import os
import itertools
import argparse
import pickle
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import pypeliner
import pypeliner.managed as mgd

import demix.simulations.pipeline
import demix.analysis.haplotype
import demix.wrappers
import demix.utils


demix_directory = os.path.realpath(os.path.join(os.path.dirname(__file__), os.pardir))
default_config_filename = os.path.join(demix_directory, 'defaultconfig.py')


if __name__ == '__main__':

    import run_comparison

    argparser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    pypeliner.app.add_arguments(argparser)

    argparser.add_argument('ref_data_dir',
        help='Reference dataset directory')

    argparser.add_argument('sim_params',
        help='Simulation Parameters Filename')

    argparser.add_argument('install_dir',
        help='Tool installation directory')

    argparser.add_argument('results_table',
        help='Output Table Filename')

    argparser.add_argument('--config', required=False,
        help='Configuration Filename')

    args = vars(argparser.parse_args())

    config = {'ref_data_directory':args['ref_data_dir']}
    execfile(default_config_filename, {}, config)

    if args['config'] is not None:
        execfile(args['config'], {}, config)

    config.update(args)

    pyp = pypeliner.app.Pypeline([demix, run_comparison], config)

    chromosomes = [str(a) for a in xrange(1, 23)]

    chromosome_lengths = dict()
    for chromosome, length in demix.utils.read_chromosome_lengths(config['genome_fai']).iteritems():
        if chromosome not in chromosomes:
            continue
        chromosome_lengths[chromosome] = length

    defaults = {
        'h_total':0.1,
        'N':1000,
        'M':3,
        'fragment_mean':300.,
        'fragment_stddev':30.,
        'read_length':100,
        'base_call_error':0.005,
        'frac_normal':0.4,
        'chromosomes':chromosomes,
        'chromosome_lengths':chromosome_lengths,
    }

    def merge_params(params, defaults):
        merged = dict()
        for idx, values in enumerate(zip(*params.values())):
            merged[idx] = dict(zip(params.keys(), values))
            for key, value in defaults.iteritems():
                merged[idx][key] = value
        return merged

    germline_params = dict()
    germline_params['random_seed'] = range(10, 10+10)
    germline_params = merge_params(germline_params, defaults)

    genome_params = dict()
    genome_params['random_seed'] = range(10, 10+4)
    genome_params['num_descendent_events'] = [10, 10, 20, 30]
    genome_params['proportion_subclonal'] = [0.15, 0.3, 0.45, 0.6]
    genome_params = merge_params(genome_params, defaults)

    mixture_params = dict()
    mixture_params['random_seed'] = range(10, 10+4)
    mixture_params['tumour_data_seed'] = range(10, 10+4)
    mixture_params['frac_clone'] = [(0.55,0.05),(0.5,0.1),(0.4,0.2),(0.3,0.3)]
    mixture_params = merge_params(mixture_params, defaults)

    # For each of n patients:
    #     * simulate germline alleles

    germline_axis = ('bygermline',)

    pyp.sch.setobj(mgd.TempOutputObj('germline_params', *germline_axis), germline_params)
    pyp.sch.setobj(mgd.TempOutputObj('chromosomes'), chromosomes)

    pyp.sch.transform('simulate_germline_alleles', germline_axis, {'mem':8},
        demix.simulations.pipeline.simulate_germline_alleles,
        None,
        mgd.TempOutputFile('germline_alleles', *germline_axis),
        mgd.TempInputObj('germline_params', *germline_axis),
        mgd.TempInputObj('chromosomes'),
        config,
    )

    # For each of n patients:
    #     For each of m genomes:
    #         * clonal divergence
    #         * normal dataset

    genome_axis = germline_axis + ('bygenome',)

    pyp.sch.setobj(mgd.TempOutputObj('genome_params', *genome_axis), genome_params, genome_axis[:-1])

    pyp.sch.transform('simulate_genomes', genome_axis, {'mem':4},
        run_comparison.simulate_genomes,
        None,
        mgd.TempOutputFile('genomes', *genome_axis),
        mgd.TempOutputFile('segment.tsv', *genome_axis),
        mgd.TempOutputFile('perfect_segment.tsv', *genome_axis),
        mgd.TempOutputFile('breakpoint.tsv', *genome_axis),
        mgd.TempInputObj('genome_params', *genome_axis),
    )

    pyp.sch.transform('simulate_normal_data', genome_axis, {'mem':16},
        demix.simulations.pipeline.simulate_normal_data,
        None,
        mgd.TempOutputFile('normal', *genome_axis),
        mgd.TempInputFile('genomes', *genome_axis),
        mgd.TempInputFile('germline_alleles', *germline_axis),
        mgd.TempFile('normal_tmp', *genome_axis),
        mgd.TempInputObj('genome_params', *genome_axis),
    )

    # For each of n patients:
    #     For each of m genomes:
    #         For each of l mixtures:
    #             * tumour dataset

    mixture_axis = genome_axis + ('bymixture',)

    pyp.sch.setobj(mgd.TempOutputObj('mixture_params', *mixture_axis), mixture_params, mixture_axis[:-1])

    pyp.sch.transform('simulate_mixture', mixture_axis, {'mem':2},
        run_comparison.simulate_mixture,
        None,
        mgd.TempOutputFile('mixture', *mixture_axis),
        mgd.TempOutputFile('mixture_plot.pdf', *mixture_axis),
        mgd.TempInputFile('genomes', *genome_axis),
        mgd.TempInputObj('mixture_params', *mixture_axis),
    )

    pyp.sch.transform('simulate_tumour_data', mixture_axis, {'mem':16},
        demix.simulations.pipeline.simulate_tumour_data,
        None,
        mgd.TempOutputFile('tumour', *mixture_axis),
        mgd.TempInputFile('mixture', *mixture_axis),
        mgd.TempInputFile('germline_alleles', *germline_axis),
        mgd.TempFile('tumour_tmp', *mixture_axis),
        mgd.TempInputObj('mixture_params', *mixture_axis),
    )

    haps_axis = genome_axis + ('bychromosome',)

    pyp.sch.setobj(mgd.OutputChunks(*haps_axis), chromosomes, haps_axis[:-1])

    pyp.sch.transform('infer_haps', haps_axis, {'mem':16},
        demix.analysis.haplotype.infer_haps,
        None,
        mgd.TempOutputFile('haps.tsv', *haps_axis),
        mgd.TempInputFile('normal', *genome_axis),
        mgd.InputInstance('bychromosome'),
        mgd.TempFile('haplotyping', *haps_axis),
        config,
    )

    pyp.sch.transform('merge_haps', genome_axis, {'mem':1},
        demix.utils.merge_tables,
        None,
        mgd.TempOutputFile('haps.tsv', *genome_axis),
        mgd.TempInputFile('haps.tsv', *haps_axis),
    )

    tool_axis = mixture_axis + ('bytool',)

    pyp.sch.transform('create_tools', mixture_axis, {'local':True},
        run_comparison.create_tools,
        mgd.TempOutputObj('tool', *tool_axis),
        args['install_dir'],
    )

    pyp.sch.transform('create_analysis', tool_axis, {'local':True},
        run_comparison.create_analysis,
        mgd.TempOutputObj('tool_analysis', *tool_axis),
        mgd.TempInputObj('tool', *tool_axis),
        mgd.TempFile('tool_tmp', *tool_axis),
    )

    init_axis = tool_axis + ('bytool',)

    pyp.sch.transform('tool_prepare', tool_axis, {'mem':8},
        run_comparison.tool_prepare,
        mgd.TempOutputObj('init_idx', *init_axis),
        mgd.TempInputObj('tool_analysis', *tool_axis),
        mgd.TempInputFile('normal', *genome_axis),
        mgd.TempInputFile('tumour', *mixture_axis),
        mgd.TempInputFile('segment.tsv', *genome_axis),
        mgd.TempInputFile('perfect_segment.tsv', *genome_axis),
        mgd.TempInputFile('breakpoint.tsv', *genome_axis),
        mgd.TempInputFile('haps.tsv', *genome_axis),
    )

    pyp.sch.transform('tool_run', init_axis, {'mem':8},
        run_comparison.tool_run,
        mgd.TempOutputObj('run_result', *init_axis),
        mgd.TempInputObj('tool_analysis', *tool_axis),
        mgd.TempInputObj('init_idx', *init_axis),
    )

    pyp.sch.transform('tool_report', tool_axis, {'mem':4},
        run_comparison.tool_report,
        None,
        mgd.TempInputObj('tool_analysis', *tool_axis),
        mgd.TempInputObj('run_result', *init_axis),
        mgd.TempOutputFile('cn.tsv', *tool_axis),
        mgd.TempOutputFile('mix.tsv', *tool_axis),
    )

    pyp.sch.transform('tabulate_results', mixture_axis, {'mem':1},
        run_comparison.tabulate_results,
        None,
        mgd.TempOutputFile('results.tsv', *mixture_axis),
        mgd.TempInputFile('cn.tsv', *tool_axis),
        mgd.TempInputFile('mix.tsv', *tool_axis),
    )

    pyp.run()

else:

    def read_sim_defs(params_filename, config):

        params = dict()
        execfile(params_filename, {}, params)

        params['chromosome_lengths'] = dict()
        for seq_id, sequence in demix.utils.read_sequences(config['genome_fasta']):
            if seq_id not in params['chromosomes']:
                continue
            params['chromosome_lengths'][seq_id] = len(sequence)

        return params


    def simulate_genomes(genomes_filename, segment_filename, perfect_segment_filename, breakpoint_filename, params):

        demix.simulations.pipeline.simulate_genomes(genomes_filename, params)
        demix.simulations.pipeline.write_segments(segment_filename, genomes_filename)
        demix.simulations.pipeline.write_perfect_segments(perfect_segment_filename, genomes_filename)
        demix.simulations.pipeline.write_breakpoints(breakpoint_filename, genomes_filename)


    def simulate_mixture(mixture_filename, plot_filename, genome_filename, params):

        demix.simulations.pipeline.simulate_mixture(mixture_filename, genome_filename, params)
        demix.simulations.pipeline.plot_mixture(plot_filename, mixture_filename)

    def set_chromosomes(sim_defs):

        return sim_defs['chromosomes']


    def create_tools(install_directory):

        tools = dict()
        for tool_name, Tool in demix.wrappers.catalog.iteritems():
            tools[tool_name] = Tool(os.path.join(install_directory, tool_name))

        return tools


    def create_analysis(tool, analysis_directory):

        return tool.create_analysis(analysis_directory)


    def tool_prepare(tool_analysis, normal_filename, tumour_filename, segment_filename, perfect_segment_filename, breakpoint_filename, haps_filename):

        num_inits = tool_analysis.prepare(
            normal_filename,
            tumour_filename,
            segment_filename=segment_filename,
            perfect_segment_filename=perfect_segment_filename,
            breakpoint_filename=breakpoint_filename,
            haplotype_filename=haps_filename
        )

        return dict(zip(xrange(num_inits), xrange(num_inits)))


    def tool_run(tool_analysis, init_idx):

        tool_analysis.run(init_idx)

        return True


    def tool_report(tool_analysis, run_results, cn_filename, mix_filename):

        tool_analysis.report(cn_filename, mix_filename)


    def tabulate_results(table_filename, cn_filenames, mix_filenames):

        with open(table_filename, 'w') as f:
            pass

