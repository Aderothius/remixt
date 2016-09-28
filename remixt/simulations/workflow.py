import pypeliner.workflow
import pypeliner.managed as mgd

import remixt.simulations.pipeline


def create_segment_simulation_workflow(
    sim_defs,
    experiment_filename,
):
    workflow = pypeliner.workflow.Workflow()

    workflow.setobj(obj=mgd.TempOutputObj('sim_defs'), value=sim_defs)

    workflow.transform(
        name='simulate_genomes',
        ctx={'mem': 4},
        func=remixt.simulations.pipeline.simulate_genomes,
        args=(
            mgd.TempOutputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_mixture',
        ctx={'mem': 1},
        func=remixt.simulations.pipeline.simulate_mixture,
        args=(
            mgd.TempOutputFile('mixture'),
            mgd.TempInputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_experiment',
        ctx={'mem': 1},
        func=remixt.simulations.pipeline.simulate_experiment,
        args=(
            mgd.OutputFile(experiment_filename),
            mgd.TempInputFile('mixture'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    return workflow
    

def create_read_simulation_workflow(
    sim_defs,
    normal_filename,
    tumour_filename,
    mixture_filename,
    breakpoint_filename,
    config,
    ref_data_dir,
):
    workflow = pypeliner.workflow.Workflow(default_ctx={'mem': 4})

    workflow.setobj(
        obj=mgd.TempOutputObj('sim_defs'),
        value=sim_defs,
    )

    workflow.transform(
        name='simulate_germline_alleles',
        ctx={'mem': 8},
        func=remixt.simulations.pipeline.simulate_germline_alleles,
        args=(
            mgd.TempOutputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
            config,
            ref_data_dir,
        ),
    )

    workflow.transform(
        name='simulate_genomes',
        func=remixt.simulations.pipeline.simulate_genomes,
        args=(
            mgd.TempOutputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_normal_data',
        ctx={'mem': 16},
        func=remixt.simulations.pipeline.simulate_normal_data,
        args=(
            mgd.OutputFile(normal_filename),
            mgd.TempInputFile('genomes'),
            mgd.TempInputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_mixture',
        func=remixt.simulations.pipeline.simulate_mixture,
        args=(
            mgd.OutputFile(mixture_filename),
            mgd.TempInputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_tumour_data',
        ctx={'mem': 16},
        func=remixt.simulations.pipeline.simulate_tumour_data,
        args=(
            mgd.OutputFile(tumour_filename),
            mgd.InputFile(mixture_filename),
            mgd.TempInputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='write_breakpoints',
        func=remixt.simulations.pipeline.write_breakpoints,
        args=(
            mgd.OutputFile(breakpoint_filename),
            mgd.InputFile(mixture_filename),
        ),
    )

    return workflow


def create_resample_simulation_workflow(
    sim_defs,
    source_filename,
    normal_filename,
    tumour_filename,
    mixture_filename,
    breakpoint_filename,
    config,
    ref_data_dir,
):
    workflow = pypeliner.workflow.Workflow(default_ctx={'mem': 4})

    workflow.setobj(
        obj=mgd.TempOutputObj('sim_defs'),
        value=sim_defs,
    )

    workflow.transform(
        name='simulate_germline_alleles',
        ctx={'mem': 8},
        func=remixt.simulations.pipeline.simulate_germline_alleles,
        args=(
            mgd.TempOutputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
            config,
            ref_data_dir,
        ),
    )

    workflow.transform(
        name='simulate_genomes',
        func=remixt.simulations.pipeline.simulate_genomes,
        args=(
            mgd.TempOutputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='resample_normal_data',
        ctx={'mem': 16},
        func=remixt.simulations.pipeline.resample_normal_data,
        args=(
            mgd.OutputFile(normal_filename),
            mgd.InputFile(source_filename),
            mgd.TempInputFile('genomes'),
            mgd.TempInputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='simulate_mixture',
        func=remixt.simulations.pipeline.simulate_mixture,
        args=(
            mgd.OutputFile(mixture_filename),
            mgd.TempInputFile('genomes'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='resample_tumour_data',
        ctx={'mem': 16},
        func=remixt.simulations.pipeline.resample_tumour_data,
        args=(
            mgd.OutputFile(tumour_filename),
            mgd.InputFile(source_filename),
            mgd.InputFile(mixture_filename),
            mgd.TempInputFile('germline_alleles'),
            mgd.TempInputObj('sim_defs'),
        ),
    )

    workflow.transform(
        name='write_breakpoints',
        func=remixt.simulations.pipeline.write_breakpoints,
        args=(
            mgd.OutputFile(breakpoint_filename),
            mgd.InputFile(mixture_filename),
        ),
    )

    return workflow

