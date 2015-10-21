import itertools
import pickle
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import remixt.segalg
import remixt.simulations.experiment
import remixt.simulations.haplotype
import remixt.cn_plot
import remixt.simulations.seqread


def read_sim_defs(sim_defs_filename):

    sim_defs = dict()
    execfile(sim_defs_filename, {}, sim_defs)

    default_settings = sim_defs['defaults']

    settings_dicts = dict()

    for name, settings in sim_defs.iteritems():

        if not name.endswith('_settings'):
            continue

        name = name[:-len('_settings')]

        permute = [zip(itertools.repeat(key), values) for key, values in settings.iteritems()]
        product = itertools.product(*permute)

        # Any settings with tuples of strings as keys represent settings
        # that are tied, multiple values are set for each single simulation
        # and these lists of settings tuples must be unzipped

        def unzip_tied_setting(key, value):
            if isinstance(key, tuple):
                if len(key) != len(value):
                    raise ValueError('incompatible key/value lengths for tied values')
                for k, v in zip(key, value):
                    yield k, v
            else:
                yield key, value

        def unzip_sim(sim):
            return itertools.chain(*[unzip_tied_setting(key, value) for key, value in sim])

        unzipped = list([dict(unzip_sim(a)) for a in product])

        settings_df = pd.DataFrame(unzipped)

        assert not settings_df.isnull().any().any()

        settings_df['name'] = name

        for key, value in default_settings.iteritems():
            if key not in settings_df:
                settings_df[key] = value

        # Sim ID as hash of settings for consistency
        settings_df['sim_hash'] = settings_df.apply(lambda row: abs(hash(frozenset(row.to_dict().items()))), axis=1).astype(str)
        assert not settings_df['sim_hash'].duplicated().any()
        settings_df['sim_id'] = settings_df['name'] + '_' + settings_df['sim_hash']

        for idx, row in settings_df.iterrows():
            settings_dicts[row['sim_id']] = row.to_dict()

    return settings_dicts


def simulate_genomes(genomes_filename, params):

    rh_sampler = remixt.simulations.experiment.RearrangementHistorySampler(params)
    gc_sampler = remixt.simulations.experiment.GenomeCollectionSampler(rh_sampler, params)

    np.random.seed(params['random_seed'])

    gc = gc_sampler.sample_genome_collection()

    with open(genomes_filename, 'w') as genomes_file:
        pickle.dump(gc, genomes_file)


def simulate_mixture(mixture_filename, genomes_filename, params):

    gm_sampler = remixt.simulations.experiment.GenomeMixtureSampler(params)

    with open(genomes_filename, 'r') as genomes_file:
        gc = pickle.load(genomes_file)

    np.random.seed(params['random_seed'])

    gm = gm_sampler.sample_genome_mixture(gc)

    with open(mixture_filename, 'w') as mixture_file:
        pickle.dump(gm, mixture_file)


def simulate_experiment(experiment_filename, mixture_filename, params):

    exp_sampler = remixt.simulations.experiment.ExperimentSampler(params)

    with open(mixture_filename, 'r') as mixture_file:
        gm = pickle.load(mixture_file)

    np.random.seed(params['random_seed'])

    exp = exp_sampler.sample_experiment(gm)

    with open(experiment_filename, 'w') as experiment_file:
        pickle.dump(exp, experiment_file)


def simulate_germline_alleles(germline_alleles_filename, params, chromosomes, config):

    haplotypes_template = config['haplotypes_template']
    legend_template = config['legend_template']

    np.random.seed(params['random_seed'])

    alleles_table = remixt.simulations.haplotype.create_sim_alleles(haplotypes_template, legend_template, chromosomes)

    alleles_table.to_csv(germline_alleles_filename, sep='\t', index=False, header=True)


def simulate_normal_data(read_data_filename, genome_filename, germline_alleles_filename, temp_dir, params):

    with open(genome_filename, 'r') as genome_file:
        gc = pickle.load(genome_file)

    germline_alleles = pd.read_csv(germline_alleles_filename, sep='\t', usecols=['chromosome', 'position', 'is_alt_0', 'is_alt_1'], dtype={'chromosome':str, 'position':np.uint32, 'is_alt_0':np.uint8, 'is_alt_1':np.uint8})

    np.random.seed(params['random_seed'])

    remixt.simulations.seqread.simulate_mixture_read_data(
        read_data_filename,
        [gc.genomes[0]],
        [params['h_total']],
        germline_alleles,
        temp_dir,
        params)


def simulate_tumour_data(read_data_filename, mixture_filename, germline_alleles_filename, temp_dir, params):

    with open(mixture_filename, 'r') as mixture_file:
        gm = pickle.load(mixture_file)

    germline_alleles = pd.read_csv(germline_alleles_filename, sep='\t', usecols=['chromosome', 'position', 'is_alt_0', 'is_alt_1'], dtype={'chromosome':str, 'position':np.uint32, 'is_alt_0':np.uint8, 'is_alt_1':np.uint8})

    np.random.seed(params['random_seed'])

    remixt.simulations.seqread.simulate_mixture_read_data(
        read_data_filename,
        gm.genome_collection.genomes,
        gm.frac * params['h_total'],
        germline_alleles,
        temp_dir,
        params)


def tabulate_experiment(exp_table_filename, sim_id, experiment_filename):

    with open(experiment_filename, 'r') as experiment_file:
        exp = pickle.load(experiment_file)

    exp_data = dict()
    exp_data['sim_id'] = sim_id

    exp_data['proportion_divergent'] = exp.genome_mixture.genome_collection.proportion_divergent()

    for idx, proportion_loh in enumerate(exp.genome_mixture.genome_collection.proportion_loh()):
        exp_data['proportion_loh_{0}'.format(idx)] = proportion_loh

    for idx, proportion_hdel in enumerate(exp.genome_mixture.genome_collection.proportion_hdel()):
        exp_data['proportion_hdel_{0}'.format(idx)] = proportion_hdel

    for idx, proportion_hlamp in enumerate(exp.genome_mixture.genome_collection.proportion_hlamp()):
        exp_data['proportion_hlamp_{0}'.format(idx)] = proportion_hlamp

    exp_table = pd.DataFrame([exp_data])

    exp_table.to_csv(exp_table_filename, sep='\t', index=False)


def plot_experiment(experiment_plot_filename, experiment_filename):

    with open(experiment_filename, 'r') as experiment_file:
        exp = pickle.load(experiment_file)

    fig = remixt.cn_plot.experiment_plot(exp, exp.cn, exp.h, exp.p)

    fig.savefig(experiment_plot_filename, format='pdf', bbox_inches='tight', dpi=300)


def plot_mixture(mixture_plot_filename, mixture_filename):

    with open(mixture_filename, 'r') as mixture_file:
        mixture = pickle.load(mixture_file)

    fig = remixt.cn_plot.mixture_plot(mixture)

    fig.savefig(mixture_plot_filename, format='pdf', bbox_inches='tight', dpi=300)


def merge_tables(output_filename, input_filenames):

    output_table = list()

    for input_filename in input_filenames.values():
        output_table.append(pd.read_csv(input_filename, sep='\t', dtype=str))

    output_table = pd.concat(output_table, ignore_index=True)

    output_table.to_csv(output_filename, sep='\t', index=False)


def tabulate_results(results_table_filename, settings, stats_table_filename, exp_table_filename):

    stats_table = pd.read_csv(stats_table_filename, sep='\t')
    exp_table = pd.read_csv(exp_table_filename, sep='\t')

    results_table = pd.DataFrame(settings.values())

    results_table = results_table.merge(stats_table, on='sim_id')
    results_table = results_table.merge(exp_table, on='sim_id')

    results_table.to_csv(results_table_filename, sep='\t', index=False)


def write_segments(segment_filename, genomes_filename):

    with open(genomes_filename, 'r') as genomes_file:
        gc = pickle.load(genomes_file)

    segment_data = pd.DataFrame({
        'chromosome':gc.segment_chromosome_id,
        'start':gc.segment_start,
        'end':gc.segment_end,
    })

    segment_data.to_csv(segment_filename, sep='\t', index=False, header=True)


def write_perfect_segments(segment_filename, genomes_filename):

    with open(genomes_filename, 'r') as genomes_file:
        gc = pickle.load(genomes_file)

    is_diff_next = (np.abs(np.diff(gc.cn, axis=0)).sum(axis=(1,2)) > 0) * 1
    is_new_seg = np.concatenate(([1], is_diff_next))
    seg_id = is_new_seg.cumsum() - 1

    segment_data = pd.DataFrame({
        'chromosome':gc.segment_chromosome_id,
        'start':gc.segment_start,
        'end':gc.segment_end,
        'seg_id':seg_id,
    })

    segment_data = (
        segment_data
        .groupby(['chromosome', 'seg_id'])
        .agg({'start':np.min, 'end':np.max})
        .reset_index()
        .drop('seg_id', axis=1)
    )

    segment_data.to_csv(segment_filename, sep='\t', index=False, header=True)


def write_breakpoints(breakpoint_filename, genomes_filename):

    with open(genomes_filename, 'r') as genomes_file:
        gc = pickle.load(genomes_file)

    breakpoint_table = list()

    for breakpoint in gc.breakpoints:

        breakpoint_row = dict()

        for idx, breakend in enumerate(breakpoint):

            n, side = breakend
            chromosome = gc.segment_chromosome_id[n]
            if side == 0:
                strand = '-'
                position = gc.segment_start[n]
            elif side == 1:
                strand = '+'
                position = gc.segment_end[n]

            breakpoint_row['chromosome_{0}'.format(idx+1)] = chromosome
            breakpoint_row['strand_{0}'.format(idx+1)] = strand
            breakpoint_row['position_{0}'.format(idx+1)] = position

        breakpoint_table.append(breakpoint_row)

    breakpoint_table = pd.DataFrame(breakpoint_table)
    breakpoint_table['prediction_id'] = xrange(len(breakpoint_table.index))

    breakpoint_table.to_csv(breakpoint_filename, sep='\t', header=True, index=False)


def compare_cn(mix_true, mix_pred, cn_true, cn_pred, segment_lengths):
    """ Compare copy number matrices

    Args:
        mix_true (numpy.array): real tumour clone mixture
        mix_pred (numpy.array): predicted tumour clone mixture
        cn_true (numpy.array): real tumour copy number
        cn_pred (numpy.array): predicted tumour copy number
        segment_lengths (numpy.array): predicted segment lengths

    """

    # Allow for clone copy number swapping if the mix fractions are close to equal
    if mix_true.min() / mix_true.max() > 0.75:
        cn_correct = (cn_true == cn_pred).all(axis=(1, 2)) | (cn_true == cn_pred[:,::-1,:]).all(axis=(1, 2))
    else:
        cn_correct = (cn_true == cn_pred).all(axis=(1, 2))

    proportion_correct = float((cn_correct * segment_lengths).sum()) / float(segment_lengths.sum())

    return proportion_correct


def evaluate_results(mixture_filename, cn_filename, mix_filename):

    with open(mixture_filename, 'r') as mixture_file:
        gm = pickle.load(mixture_file)

    cn_data = pd.read_csv(cn_filename, sep='\t', converters={'chromosome':str})

    sim_segments = pd.DataFrame({
        'chromosome':gm.segment_chromosome_id,
        'start':gm.segment_start,
        'end':gm.segment_end,
    })

    if 'major_1' in cn_data:

        cn_true = gm.cn[:,1:,:]

        cn_pred = np.array(
            [
                [cn_data['major_1'], cn_data['minor_1']],
                [cn_data['major_2'], cn_data['minor_2']],
            ]
        ).swapaxes(0, 2).swapaxes(1, 2)

    else:

        cn_true = np.zeros((gm.cn.shape[0], gm.cn.shape[1]-1, 1))

        cn_true[:,:,0] = gm.cn[:,1:,:].sum(axis=2)

        cn_pred = np.array(
            [
                [cn_data['total_1']],
                [cn_data['total_2']],
            ]
        ).swapaxes(0, 2).swapaxes(1, 2)

    mix_true = gm.frac
    with open(mix_filename, 'r') as mix_file:
        mix_pred = np.array(mix_file.readline().split()).astype(float)

    # Ensure true tumour clones are consistent, largest first
    order_true = np.argsort(mix_true[1:])[::-1]
    mix_true[1:] = mix_true[order_true]
    cn_true = cn_true[:,order_true,:]

    # Ensure predicted tumour clones are consistent, largest first
    order_pred = np.argsort(mix_pred[1:])[::-1]
    mix_pred[1:] = mix_pred[order_pred]
    cn_pred = cn_pred[:,order_pred,:]

    # Ensure major minor ordering is consistent
    cn_true = np.sort(cn_true, axis=2)
    cn_pred = np.sort(cn_pred, axis=2)

    cn_data_index = remixt.segalg.reindex_segments(sim_segments, cn_data)

    cn_true = cn_true[cn_data_index['idx_1'].values,:,:]
    cn_pred = cn_pred[cn_data_index['idx_2'].values,:,:]
    segment_lengths = (cn_data_index['end'] - cn_data_index['start']).values

    proportion_cn_correct = remixt.simulations.pipeline.compare_cn(
        mix_true[1:], mix_pred[1:], cn_true, cn_pred, segment_lengths)

    is_dom_cn_correct = np.all(cn_true[:,0,:] == cn_pred[:,0,:], axis=1)

    proportion_dom_cn_correct = float((is_dom_cn_correct * segment_lengths).sum()) / float(segment_lengths.sum())

    is_clonal_true = np.all(cn_true[:,0:1,:].swapaxes(1, 2) == cn_true[:,:,:].swapaxes(1, 2), axis=(1, 2))
    is_clonal_pred = np.all(cn_pred[:,0:1,:].swapaxes(1, 2) == cn_pred[:,:,:].swapaxes(1, 2), axis=(1, 2))
    is_clonal_correct = is_clonal_true == is_clonal_pred
    is_subclonal_correct = ~is_clonal_true == ~is_clonal_pred

    proportion_clonal_correct = float((is_clonal_correct * segment_lengths).sum()) / float(segment_lengths.sum())
    proportion_subclonal_correct = float((is_subclonal_correct * segment_lengths).sum()) / float(segment_lengths.sum())

    results = dict()

    results['proportion_cn_correct'] = proportion_cn_correct
    results['proportion_dom_cn_correct'] = proportion_dom_cn_correct
    results['proportion_clonal_correct'] = proportion_clonal_correct
    results['proportion_subclonal_correct'] = proportion_subclonal_correct

    for idx, f in enumerate(mix_true):
        results['mix_true_'+str(idx)] = f

    for idx, f in enumerate(mix_pred):
        results['mix_pred_'+str(idx)] = f

    return results




