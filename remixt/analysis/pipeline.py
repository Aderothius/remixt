import pickle
import itertools
import numpy as np
import pandas as pd

import remixt.config
import remixt.likelihood
import remixt.cn_model
import remixt.em
import remixt.genome_graph
import remixt.analysis.experiment
import remixt.analysis.readdepth


def init(
    init_results_filename,
    experiment_filename,
    config,
):
    min_ploidy = remixt.config.get_param(config, 'min_ploidy')
    max_ploidy = remixt.config.get_param(config, 'max_ploidy')
    tumour_mix_fractions = remixt.config.get_param(config, 'tumour_mix_fractions')
    divergence_weights = remixt.config.get_param(config, 'divergence_weights')

    with open(experiment_filename, 'r') as f:
        experiment = pickle.load(f)

    # Calculate candidate haploid depths for normal contamination and a single
    # tumour clone based on modes of the minor allele depth
    read_depth = remixt.analysis.readdepth.calculate_depth(experiment)
    minor_modes = remixt.analysis.readdepth.calculate_minor_modes(read_depth)
    init_h_mono = remixt.analysis.readdepth.calculate_candidate_h_monoclonal(minor_modes)

    # Calculate candidate haploid depths for normal contamination and multiple clones
    # Filter candidates with inappropriate ploidy
    init_h_params = []
    for mode_idx, h_mono in enumerate(init_h_mono):
        for mix_frac in tumour_mix_fractions:
            mix_frac = np.array(mix_frac)
            h_poly = np.array([h_mono[0]] + list(h_mono[1] * mix_frac))

            estimated_ploidy = remixt.analysis.readdepth.estimate_ploidy(h_poly, experiment)

            if min_ploidy is not None and estimated_ploidy < min_ploidy:
                continue

            if max_ploidy is not None and estimated_ploidy > max_ploidy:
                continue

            params = {'mode_idx': mode_idx, 'h_init': tuple(h_poly)}
            init_h_params.append(params)

    # Attempt several divergence parameters
    init_params = []
    divergence_weight_params = [{'divergence_weight': w} for w in divergence_weights]
    for h_p, w_p in itertools.product(init_h_params, divergence_weight_params):
        params = h_p.copy()
        params.update(w_p)
        init_params.append(params)

    with pd.HDFStore(init_results_filename, 'w') as store:
        store['read_depth'] = read_depth
        store['minor_modes'] = pd.Series(minor_modes, index=xrange(len(minor_modes)))

    return dict(enumerate(init_params))


def fit_hmm_viterbi(experiment, emission, prior, h_init, max_copy_number, normal_contamination):
    N = experiment.l.shape[0]
    M = h_init.shape[0]

    results = dict()
    results['stats'] = dict()

    # Initialize haploid depths
    emission.h = h_init

    model = remixt.cn_model.HiddenMarkovModel(N, M, emission, prior, experiment.chains, max_copy_number=max_copy_number, normal_contamination=normal_contamination)

    # Estimate haploid depths and overdispersion parameters
    estimator = remixt.em.ExpectationMaximizationEstimator()
    log_likelihood = estimator.learn_param(
        model,
        emission.h_param,
        emission.r_param,
        emission.M_param,
        emission.z_param,
        emission.hdel_mu_param,
        emission.loh_p_param,
    )
    results['h'] = emission.h
    results['r'] = emission.r
    results['M'] = emission.M
    results['stats']['h_log_likelihood'] = log_likelihood
    results['stats']['h_converged'] = estimator.converged
    results['stats']['h_em_iter'] = estimator.em_iter
    results['stats']['h_error_message'] = estimator.error_message

    # Infer copy number from viterbi
    log_likelihood_viterbi, cn = model.optimal_state()

    # Naive breakpoint copy number
    brk_cn = remixt.cn_model.decode_breakpoints_naive(cn, experiment.adjacencies, experiment.breakpoints)

    # Infer copy number
    results['cn'] = cn
    results['brk_cn'] = brk_cn
    results['stats']['viterbi_log_likelihood'] = log_likelihood_viterbi
    results['stats']['log_likelihood'] = log_likelihood_viterbi
    results['stats']['log_prior'] = prior.log_prior(cn).sum()

    return results


def fit_hmm_graph(experiment, emission, prior, h_init, max_copy_number, normal_contamination):
    N = experiment.l.shape[0]
    M = h_init.shape[0]

    results = dict()
    results['stats'] = dict()

    # Initialize haploid depths
    emission.h = h_init

    model = remixt.cn_model.HiddenMarkovModel(N, M, emission, prior, experiment.chains, max_copy_number=max_copy_number, normal_contamination=normal_contamination)

    # Estimate haploid depths
    estimator = remixt.em.ExpectationMaximizationEstimator()
    log_likelihood = estimator.learn_param(
        model,
        emission.h_param,
        emission.r_param,
        emission.M_param,
        emission.z_param,
        emission.hdel_mu_param,
        emission.loh_p_param,
    )
    results['h'] = emission.h
    results['r'] = emission.r
    results['M'] = emission.M
    results['stats']['h_log_likelihood'] = log_likelihood
    results['stats']['h_converged'] = estimator.converged
    results['stats']['h_em_iter'] = estimator.em_iter
    results['stats']['h_error_message'] = estimator.error_message

    # Set to allele independent prior as allele dependence will
    # cause the genome graph algorithm to fail
    prior.allele_specific = False

    # Infer copy number from viterbi
    _, cn_init = model.optimal_state()

    # Create genome graph initializing from viterbi
    graph = remixt.genome_graph.GenomeGraph(emission, prior, experiment.adjacencies, experiment.breakpoints)
    graph.set_observed_data(experiment.x, experiment.l)
    graph.init_copy_number(cn_init)

    # Infer copy number
    log_likelihood_graph, cn = graph.optimize()
    results['cn'] = cn
    results['brk_cn'] = graph.breakpoint_copy_number
    results['stats']['graph_opt_iter'] = graph.opt_iter
    results['stats']['graph_log_likelihood'] = log_likelihood_graph
    results['stats']['graph_decreased_log_posterior'] = graph.decreased_log_posterior
    results['stats']['log_likelihood'] = log_likelihood_graph
    results['stats']['log_prior'] = prior.log_prior(cn).sum()

    return results


def fit_graph(experiment, emission, prior, h_init, max_copy_number, normal_contamination):
    N = experiment.l.shape[0]
    M = h_init.shape[0]

    results = dict()
    results['stats'] = dict()

    # Infer initial copy number from viterbi with 1 tumour clone
    h_init_single = np.zeros((2,))
    h_init_single[0] = h_init[0]
    h_init_single[1] = h_init[1:].sum()
    emission.h = h_init_single
    model = remixt.cn_model.HiddenMarkovModel(N, 2, emission, prior, experiment.chains, max_copy_number=max_copy_number, normal_contamination=normal_contamination)
    _, cn = model.optimal_state()
    cn_init = np.ones((N, M, 2))
    for m in xrange(1, M):
        cn_init[:,m,:] = cn[:,1,:]

    # Initialize haploid depths
    emission.h = h_init

    # Create genome graph
    graph = remixt.genome_graph.GenomeGraph(emission, prior, experiment.adjacencies, experiment.breakpoints)
    graph.set_observed_data(experiment.x, experiment.l)
    graph.init_copy_number(cn_init)

    # Estimate haploid depths and copy number
    estimator = remixt.em.HardAssignmentEstimator()
    h, log_likelihood, h_converged = estimator.learn_param(graph, 'h', h_init)

    results['h'] = h
    results['cn'] = graph.cn
    results['brk_cn'] = graph.breakpoint_copy_number
    results['stats']['h_em_iter'] = estimator.em_iter
    results['stats']['graph_opt_iter'] = graph.opt_iter
    results['stats']['graph_log_likelihood'] = log_likelihood
    results['stats']['graph_decreased_log_posterior'] = graph.decreased_log_posterior
    results['stats']['log_likelihood'] = log_likelihood
    results['stats']['log_prior'] = prior.log_prior(graph.cn).sum()

    return results


fit_methods = [
    'hmm_viterbi',
    'hmm_graph',
    'graph',
]


def fit(
    results_filename,
    experiment_filename,
    init_params,
    config,
    ref_data_dir,
):
    fit_method = remixt.config.get_param(config, 'fit_method')
    normal_contamination = remixt.config.get_param(config, 'normal_contamination')

    likelihood_min_segment_length = remixt.config.get_param(config, 'likelihood_min_segment_length')
    likelihood_min_proportion_genotyped = remixt.config.get_param(config, 'likelihood_min_proportion_genotyped')
    max_copy_number = remixt.config.get_param(config, 'max_copy_number')

    with open(experiment_filename, 'r') as f:
        experiment = pickle.load(f)

    h_init = np.array(init_params['h_init'])
    divergence_weight = init_params['divergence_weight']

    # Create emission / prior / copy number models
    emission = remixt.likelihood.NegBinBetaBinLikelihood(experiment.x, experiment.l)
    emission.h = h_init

    # Create prior probability model
    prior = remixt.cn_model.CopyNumberPrior(experiment.l, divergence_weight=divergence_weight)

    # Mask amplifications and poorly modelled segments from likelihood
    emission.add_amplification_mask(max_copy_number)
    emission.add_segment_length_mask(likelihood_min_segment_length)
    emission.add_proportion_genotyped_mask(likelihood_min_proportion_genotyped)

    if fit_method == 'hmm_viterbi':
        fit_results = fit_hmm_viterbi(experiment, emission, prior, h_init, max_copy_number, normal_contamination)
    elif fit_method == 'hmm_graph':
        fit_results = fit_hmm_graph(experiment, emission, prior, h_init, max_copy_number, normal_contamination)
    elif fit_method == 'graph':
        fit_results = fit_graph(experiment, emission, prior, h_init, max_copy_number, normal_contamination)
    else:
        raise ValueError('unknown fit method {}'.format(fit_method))

    h = fit_results['h']
    cn = fit_results['cn']
    brk_cn = fit_results['brk_cn']

    # Create copy number table
    cn_table = experiment.create_cn_table(emission, cn, h)
    cn_table['log_likelihood'] = emission.log_likelihood(cn)
    cn_table['log_prior'] = prior.log_prior(cn)
    cn_table['major_expected'] = emission.expected_read_count(experiment.l, cn)[:,0]
    cn_table['minor_expected'] = emission.expected_read_count(experiment.l, cn)[:,1]
    cn_table['total_expected'] = emission.expected_read_count(experiment.l, cn)[:,2]
    cn_table['ratio_expected'] = emission.expected_allele_ratio(cn)
    cn_table['major_residual'] = np.absolute(cn_table['major_readcount'] - cn_table['major_expected'])
    cn_table['minor_residual'] = np.absolute(cn_table['minor_readcount'] - cn_table['minor_expected'])
    cn_table['total_residual'] = np.absolute(cn_table['readcount'] - cn_table['total_expected'])

    # Create copy number table
    # Account for both orderings of the two breakends
    column_swap = {
        'n_1':'n_2',
        'ell_1':'ell_2',
        'side_1':'side_2',
        'n_2':'n_1',
        'ell_2':'ell_1',
        'side_2':'side_1', 
    }
    brk_cn_table_1 = brk_cn.merge(experiment.breakpoint_segment_data)
    brk_cn_table_2 = brk_cn.merge(experiment.breakpoint_segment_data.rename(columns=column_swap))
    brk_cn_table = pd.concat([brk_cn_table_1, brk_cn_table_2], ignore_index=True)

    ploidy = (cn[:,1:,:].mean(axis=1).T * experiment.l).sum() / experiment.l.sum()
    divergent = (cn[:,1:,:].max(axis=1) != cn[:,1:,:].min(axis=1)) * 1.
    proportion_divergent = (divergent.T * experiment.l).sum() / (2. * experiment.l.sum())

    # Create a table of relevant statistics
    stats_table = fit_results['stats'].copy()
    stats_table['num_clones'] = len(h),
    stats_table['num_segments'] = len(experiment.x),
    stats_table['ploidy'] = ploidy
    stats_table['proportion_divergent'] = proportion_divergent
    stats_table['mode_idx'] = init_params['mode_idx']
    stats_table['divergence_weight'] = init_params['divergence_weight']
    stats_table = pd.DataFrame(stats_table, index=[0])

    # Store in hdf5 format
    with pd.HDFStore(results_filename, 'w') as store:
        store['stats'] = stats_table
        store['h_init'] = pd.Series(h_init, index=xrange(len(h)))
        store['h'] = pd.Series(h, index=xrange(len(h)))
        store['cn'] = cn_table
        store['brk_cn'] = brk_cn_table
        store['negbin_r'] = pd.Series(emission.r, index=xrange(len(emission.r)))
        store['betabin_M'] = pd.Series(emission.M, index=xrange(len(emission.M)))


def collate(collate_filename, experiment_filename, init_results_filename, fit_results_filenames):

    # Extract the statistics for selecting solutions
    stats_table = list()
    for init_id, results_filename in fit_results_filenames.iteritems():
        with pd.HDFStore(results_filename, 'r') as results:
            stats = results['stats']
            stats['init_id'] = init_id
            stats_table.append(stats)
    stats_table = pd.concat(stats_table, ignore_index=True)

    # Select the solution that maximizes the likelihood for a given mode of the
    # minor read depth (mode_idx) and prior on divergence (divergence_weight)
    stats_table.sort('log_likelihood', ascending=False, inplace=True)
    stats_table = stats_table.groupby(['mode_idx', 'divergence_weight'], sort=False).first().reset_index()

    # Write out selected solutions
    with pd.HDFStore(collate_filename, 'w') as collated:
        collated['stats'] = stats_table

        with pd.HDFStore(init_results_filename, 'r') as results:
            for key, value in results.iteritems():
                collated[key] = results[key]

        for init_id, results_filename in fit_results_filenames.iteritems():
            if init_id not in stats_table['init_id']:
                pass

            with pd.HDFStore(results_filename, 'r') as results:
                for key, value in results.iteritems():
                    collated['solutions/solution_{0}/{1}'.format(init_id, key)] = results[key]

        with open(experiment_filename, 'r') as f:
            experiment = pickle.load(f)

        collated['breakpoints'] = experiment.breakpoint_data
        collated['reference_adjacencies'] = pd.DataFrame(list(experiment.adjacencies), columns=['n_1', 'n_2'])
        collated['breakpoint_adjacencies'] = experiment.breakpoint_segment_data


