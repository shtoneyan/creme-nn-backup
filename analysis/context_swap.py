import glob
import pickle
import pandas as pd
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt
import pyranges as pr
import sys, os, h5py
import kipoiseq
from tqdm import tqdm
import json

sys.path.append('../creme')
import creme
import custom_model
import utils
import glob


def main():
    model_name = sys.argv[1]
    data_dir = '../data/'
    result_dir = f'../results/'
    csv_dir = f'../results/summary_csvs/{model_name}/'

    print(f'USING model {model_name}')
    if model_name.lower() == 'enformer':
        track_index = [4824, 5110, 5111]
        model = custom_model.Enformer(track_index=track_index)
        target_df = pd.read_csv(f'{data_dir}/enformer_targets_human.txt', sep='\t')
        cell_lines = [utils.clean_cell_name(target_df.iloc[t]['description']) for t in track_index]
        tss_tile = [model.seq_length // 2 - 2500, model.seq_length // 2 + 2500]

    # elif model_name.lower() == 'borzoi':
    #     target_df = pd.read_csv('../data/borzoi_targets_human.txt', sep='\t')
    #     cage_rna_tracks = [i for i, t in enumerate(target_df['description']) if 'CAGE' in t or 'RNA' in t]
    #     model = custom_model.Borzoi('../data/borzoi/*/*', cage_rna_tracks, True)

    else:
        print('Unkown model')
        sys.exit(1)

    fasta_path = f'{data_dir}/GRCh38.primary_assembly.genome.fa'
    seq_parser = utils.SequenceParser(fasta_path)

    results_dir = utils.make_dir(f'{result_dir}/context_swap_test/')
    test_results_dir = utils.make_dir(f'{results_dir}/{model_name}/')


    dfs = {cell_line: pd.read_csv(f'{csv_dir}/{cell_line}_selected_contexts.csv') for
           cell_line in cell_lines}

    for cell, df in dfs.items():
        df = df.sample(frac=1)
        cell_line_dir = utils.make_dir(f'{test_results_dir}/{cell}')
        sequences = {}
        for i, row in tqdm(df.iterrows()):
            # get sequence from reference genome and convert to one-hot
            seq_info = row['path'].split('/')[-1].split('.')[0]
            chrom, start, strand = seq_info.split('_')[1:]
            sequences[seq_info] = seq_parser.extract_seq_centered(chrom, int(start), strand, model.seq_length,
                                                                  onehot=True)

        for src_seq_info, src_seq in tqdm(sequences.items(), total=len(sequences.keys())):
            for dest_seq_info, dest_seq in sequences.items():

                result_path = f'{cell_line_dir}/src_{src_seq_info}_dest_{dest_seq_info}.pickle'

                if not os.path.isfile(result_path):
                    pred_mut = creme.context_swap_test(model, src_seq, dest_seq, tss_tile)
                    utils.save_pickle(result_path, pred_mut)

    result_summary = []
    bin_index = [447, 448]
    for cell_index, cell_line in enumerate(cell_lines):
        # result_files = glob.glob(f'{results_dir}/{cell_line}/*')
        df_context = pd.read_csv(f'../results/summary_csvs/{model_name}/{cell_line}_selected_contexts.csv')
        df_context['source_id'] = [p.split('/')[-1].split('.')[0] for p in df_context['path']]
        # context_id = dict(zip(df_context['source_id'], df_context['context']))
        preds = []
        for i, row_src in tqdm(df_context.iterrows()):
            res = utils.read_pickle(
                f'{test_results_dir}/{cell_line}/src_{row_src["source_id"]}_dest_{row_src["source_id"]}.pickle')

            src_wt = res[0, bin_index, cell_index].mean()
            for j, row_dest in df_context.iterrows():
                res = utils.read_pickle(
                    f'../results/context_swap_test/enformer/{cell_line}/src_{row_src["source_id"]}_dest_{row_dest["source_id"]}.pickle')
                preds.append([row_src["source_id"], row_src['context'],
                              row_dest["source_id"], row_dest['context'],
                              res[0, bin_index, cell_index].mean() / src_wt])
        df = pd.DataFrame(preds)
        df.columns = ['source', 'source_context', 'target', 'target_context', 'normalised']
        df['cell_line'] = cell_line
        result_summary.append(df)
    result_summary = pd.concat(result_summary)
    result_summary.to_csv(f'../results/summary_csvs/{model_name}/context_swap_test.csv')

if __name__ == '__main__':
    main()
