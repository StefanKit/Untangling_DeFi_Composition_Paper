#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Created on Mon Aug 30 10:00:00 2021

@author: saggesep
"""

from sklearn.metrics.cluster import normalized_mutual_info_score
import pandas as pd
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import graph_tool.all as gt
import networkx as nx
import igraph as ig
import os
import time
import yaml
import random

import warnings
warnings.filterwarnings("ignore")

# https://github.com/igraph/igraph/issues/512 --> issues with
ig.default_arpack_options.maxiter = 5000
ig.default_arpack_options.tol = 0.1

# in order to have a correct output with to_latex and long strings
pd.set_option('display.max_colwidth', None)

with open('config.yaml', 'r') as f:
    doc = yaml.safe_load(f)

path_output = doc["output"]["path_output"]
path_figures = doc["figures"]["path_figures"]
path_tables = doc["tables"]["path_tables"]
path_colors = doc["files"]["path_prot_colors"]
path_preprocess = doc["files"]["path_preprocess_data"]
path_chain = doc["files"]["path_chain_data"]

#-----------------------------------------------------------------------------


def load_files(namefile, block_st, block_end, from_node = 'from_address', to_node = 'to_address'):

    if (namefile == 'defi_ca_network'):
        df = pd.read_csv(path_preprocess + '/defi_networks/defi_ca_network_{}-{}.csv.gz'.format(block_st,block_end))
    elif (namefile == 'defi_ca_network_pro'):
        df = pd.read_csv(path_preprocess + '/defi_networks/defi_ca_network_pro_{}-{}.csv.gz'.format(block_st,block_end))

    # create mapping from node names to ids
    vertex_id_map = pd.concat([df[from_node], df[to_node]]).drop_duplicates().reset_index(drop=True)
    vertex_id_map = vertex_id_map.reset_index(name="address").rename(columns={"index": "id"})

    dict1 = pd.Series(df.from_protocol.values, index=df.from_address).to_dict()
    dict2 = pd.Series(df.to_protocol.values, index=df.to_address).to_dict()
    dict_addrs = {**dict1, **dict2}
    vertex_id_map = vertex_id_map.join(pd.DataFrame.from_dict(dict_addrs, orient='index', columns=['protocol']), on='address')

    # translate df to use ids instead of node names
    df = vertex_id_map.rename(columns={"id": "from", "address": from_node}).merge(df, on=from_node)
    df = vertex_id_map.rename(columns={"id": "to", "address": to_node}).merge(df, on=to_node)

    if namefile == "defi_ca_network_pro":
        g_small = gt.Graph(directed=True)
        df_small = df[["from", "to","protocol_x","protocol_y"]].copy().dropna()
        df_small['prot_x'] = df_small['protocol_x'].rank(method='dense', ascending=True).astype(int)
        df_small['prot_y'] = df_small['protocol_y'].rank(method='dense', ascending=True).astype(int)
        g_small.add_edge_list(df_small[["prot_x", "prot_y"]].values)
        assortat = gt.scalar_assortativity(g_small,'total')[0]
        reciprocity = gt.edge_reciprocity(g_small)
        with open(path_tables + '/only_protocols.txt'.format(namefile), "w") as file:
            file.write(f'Reciprocity: {round(reciprocity, 3)}\n')
            file.write(f'Assortativity: {round(assortat, 3)}\n\n')

    df = df[["from", "to"]]

    # Define Graph
    g = gt.Graph(directed=True)
    # Add Edges
    g.add_edge_list(df.values)

    return (df,vertex_id_map,g)

#--------------- 5.0 - Summary table --------------------------------------------


def table_metrics(df, g, namefile):

    n_nodes = g.num_vertices()
    n_edges = g.num_edges()

    avg_k = n_edges / n_nodes
    n_self = len(df[df['from']==df['to']])

    density = n_edges/(n_nodes*(n_nodes-1))

    reciprocity = gt.edge_reciprocity(g)

    assortat = gt.scalar_assortativity(g,'total')[0]

    with open(path_tables + '/{}_summary.txt'.format(namefile), "w") as file:
        file.write('Network summary metrics. \n\n')
        file.write(f'Number of nodes: {n_nodes}. Number of edges: {n_edges}\n')
        file.write(f'Average degree: {round(avg_k, 3)}\n')  # NB: m/n (directed))
        file.write(f'Number of self-loops: {n_self}\n')
        file.write(f'Density: {density:.3e}\n')
        file.write(f'Reciprocity: {round(reciprocity, 3)}\n')
        file.write(f'Assortativity: {round(assortat,3)}\n\n\n')


#--------------- 5.1 - Degree distribution --------------------------------------------

def data_for_r(g,namefile):

    tot_degs = g.get_total_degrees(g.get_vertices())
    data1 = sorted(list(tot_degs), reverse=True)
    pd.Series(data1).to_csv(path_tables + '/' + namefile + "_degree.csv")


def tab_degrees(g, vertex_id_map, path_tables, namefile):

    deg = pd.DataFrame({'in_degree': g.get_in_degrees(g.get_vertices()),
                        'out_degree': g.get_out_degrees(g.get_vertices()), 'degree': g.get_total_degrees(g.get_vertices())})

    deg = deg.join(vertex_id_map[['id','address','protocol']])

    deg.sort_values(by=['degree'], ascending=False, inplace=True)

    table = deg[['address','protocol', 'degree', 'in_degree', 'out_degree']].head(15).set_index('address')

    header = ['Address', 'Protocol', 'Degree', 'In degree', 'Out degree']

    path = path_tables + '/{}_first15by_degrees.tex'.format(namefile)

    table.reset_index().to_latex(path, index=False, header=header)


#--------------- 5.2 - Components --------------------------------------------


def count_dim_comps(df, g, vertex_id_map, namefile, n_comps = 3):

    comp_s, hist_s = gt.label_components(g, directed=True)
    comp_w, hist_w = gt.label_components(g, directed=False)

    results = []
    index = [('Weak', '# components'), ('Weak', '# nodes'), ('Weak', '# edges'),
             ('Strong', '# components')]  # ,('Strong','# nodes'),('Strong','# edges')]

    # Weakly largest component
    wlc = gt.extract_largest_component(g, directed=False, prune=True)

    # 1) Nr. of components
    results.append(len(hist_w))

    # 2) Nr. nodes/edges in largest component
    results.append(wlc.num_vertices())
    results.append(wlc.num_edges())

    # Stongly largest components

    # 1) Nr. of components
    results.append(len(hist_s))

    # 2) Nr. edges and vertices for the strongly largest components

    # 2a) make a dataframe with info on IDs and components (ranked by dimension)
    df_comp_s = pd.DataFrame({"id": g.get_vertices(), 'component': comp_s.get_array()}).merge(vertex_id_map)
    map_comps_to_rank = pd.DataFrame(hist_s, columns=['n_nodes'])
    map_comps_to_rank['rank'] = map_comps_to_rank['n_nodes'].rank(method='first', ascending=False).astype(int)
    map_comps_to_rank['rank_min'] = map_comps_to_rank['n_nodes'].rank(method='min', ascending=False).astype(int)  #
    df_comp_s = df_comp_s.merge(map_comps_to_rank.reset_index(), left_on='component', right_on='index').drop(
        ['index'], axis=1)
    df_comp_s.sort_values(by='id', inplace=True)

    # 2b) loop over largest components

    for n in range(1,1+n_comps):

        vertices = list(df_comp_s.loc[df_comp_s['rank'] == n, 'id'])  # now rank is OK --> rank != rank_min

        df_temp = df[df.isin(vertices)].dropna().astype(int)

        # Define Graph
        g_temp = gt.Graph(directed=True)
        # Add Edges
        g_temp.add_edge_list(df_temp.values, hashed=True)

        # 2c) num vertices, num edges
        results.append(g_temp.num_vertices())
        results.append(g_temp.num_edges())

        index.append(('Strong', '# nodes comp{}'.format(n)))
        index.append(('Strong', '# edges comp{}'.format(n)))

    # 3) output as table
    toframe = pd.DataFrame(results, pd.MultiIndex.from_tuples(index)).T
    path = path_tables + '/{}_components_summary.tex'.format(namefile)
    toframe.to_latex(path, index=False)

    return df_comp_s



def stats_comps_prot(df_comp_s, namefile):

    df_comp_s_f = df_comp_s.dropna()
    comp_list = df_comp_s_f['component'].unique()  # with contract: length = 1185079

    table_1 = []

    for comp in comp_list:  # this chooses the components that include one protocol (ok for prot, not for contract?)
        nodes = len(df_comp_s[df_comp_s['component'] == comp])
        rank = int(df_comp_s.loc[df_comp_s['component'] == comp, 'rank'].median())
        rank_min = int(df_comp_s.loc[df_comp_s['component'] == comp, 'rank_min'].median())

        prots = ', '.join(list(df_comp_s_f.loc[df_comp_s_f['component'] == comp, 'protocol'].unique()))
        table_1.append([nodes, rank, rank_min, prots])


    toframe = pd.DataFrame(table_1, columns=['Nr. Nodes', 'Rank', 'Rank (min)', 'List of Protocols'])
    path = path_tables + '/{}_s_components.tex'.format(namefile)
    toframe.to_latex(path, index=False)

def plot_heatmap(df_comp_s, namefile, comps_toplot=10):
    # init df & other vars
    heatmap_df = pd.DataFrame()

    for n in range(1, 1 + comps_toplot):
        df_comp_temp = df_comp_s[df_comp_s['rank'] == n].copy()
        df_comp_temp['protocol'].fillna('Unknown', inplace=True)
        to_concat = (df_comp_temp.protocol.value_counts()).T.rename('{}({})'.format(n, len(df_comp_temp)))
        heatmap_df = pd.concat([heatmap_df, to_concat], axis=1).fillna(0)

        # alternative to using number of components in xticklabels:
        #https://stackoverflow.com/questions/33379261/how-can-i-have-a-bar-next-to-python-seaborn-heatmap-which-shows-
        # the-summation-of
        # https://stackoverflow.com/questions/34298052/how-to-add-column-next-to-seaborn-heat-map


    heatmap_df.sort_index(inplace=True)
    #move unknown to first row
    heatmap_df = pd.concat([heatmap_df.loc['Unknown'].to_frame().T, heatmap_df.drop('Unknown', axis=0)], axis=0)

    # dump to csv for r
    heatmap_df.to_csv(path_tables + '/' + namefile + "_comps_heatmap.csv")


def components(df,g,vertex_id_map,namefile):

    #make table with stats for main components;
    #returns dataframe with infos on largest components
    df_comp_s = count_dim_comps(df, g, vertex_id_map,namefile)

    # 3) inspect the largest components
    # --> Which protocols in which components?

    if namefile == 'defi_ca_network_pro':

        stats_comps_prot(df_comp_s, namefile)

    if namefile == 'defi_ca_network':

        plot_heatmap(df_comp_s, namefile)


#--------------- 5.3 - Communities --------------------------------------------

def communities(g,vertex_id_map, df_cols, namefile):

    # select only wlc: some algos work only on that
    l = gt.label_largest_component(g,directed=False)
    vertex_id_map['max_comp'] = l.a
    vim = vertex_id_map[vertex_id_map['max_comp']==1].reset_index(drop = True).copy()


    # run on Weakly largest component
    wlc = gt.extract_largest_component(g, directed=False, prune=True)
    wlc_i = ig.Graph.from_graph_tool(wlc)  # karate network:Gm2 = ig.Graph.Famous('Zachary')
    wlc_i.to_undirected()

    #rseed = 0
    #random.seed(i)
    vim = detect_communities(wlc_i, vim)

    # g_i = ig.Graph.from_graph_tool(g)
    # g_i.to_undirected()
    #vertex_id_map = detect_communities(g_i, vertex_id_map)

    community_stats(vim, namefile)

    #sankey_with_nan(vim,df_cols)
    #sankey_without_nan(vim,df_cols)


def detect_communities(i_graph, vim):

    tic = time.time()
    louvain = ig.Graph.community_multilevel(i_graph) # a version of Louvain
    membership_l = louvain.membership
    vim['louvain'] = membership_l
    toc = time.time()
    #print('Time (seconds) to compute louvain: ', round(toc - tic, 6))  # 0.0..

    # improvement of multilevel (BUT before implementing it, check/change params!!)
    tic = time.time()
    leiden = ig.Graph.community_leiden(i_graph, objective_function='modularity')
    membership = leiden.membership
    vim['leiden'] = membership
    toc = time.time()
    #print('Time (seconds) to compute leiden: ', round(toc - tic, 6))  # 0.0..

    tic = time.time()
    label_prop = ig.Graph.community_label_propagation(i_graph)
    membership = label_prop.membership
    vim['label_prop'] = membership
    toc = time.time()
    #print('Time (seconds) to compute label propagation: ', round(toc - tic, 6))

    try:
        # fast (alpha 1.12), NOT suggested (bad with...)
        ## NB: wlc because this one wasn't working with the other one!
        tic = time.time()
        eigenvec = ig.Graph.community_leading_eigenvector(i_graph)
        membership = eigenvec.membership
        vim['eigenvector'] = membership
        toc = time.time()
        #print('Time (seconds) to compute eigenvector: ', round(toc - tic, 6))  # 4.13
    except:
        print("community_leading_eigenvector algorithm didn't converge")

    return(vim)


def community_stats(vim, namefile, comm_algs = ['louvain', 'leiden', 'label_prop','eigenvector']):

    # test NMI
    vim_notna = vim[vim['protocol'].notna()].copy()
    prots = list(vim_notna.protocol.unique())
    vim_notna['prot_nr'] = vim_notna['protocol'].map({value:key for (key,value) in enumerate(prots)})

    df_avgs = pd.DataFrame()

    for comm_alg in comm_algs:

        comms = list(vim_notna[comm_alg].unique())
        all_comms = list(vim[comm_alg].unique())

        # prec,rec,f1score
        best_scores = []

        for prot in prots:

            scores = []

            for comm in comms:

                try:
                    TP = len(vim_notna[(vim_notna[comm_alg] == comm) & (vim_notna['protocol'] == prot)])
                    FP = len(vim_notna[(vim_notna[comm_alg] == comm) & (vim_notna['protocol'] != prot)])
                    FN = len(vim_notna[(vim_notna[comm_alg] != comm) & (vim_notna['protocol'] == prot)])
                    TN = len(vim_notna[(vim_notna[comm_alg] != comm) & (vim_notna['protocol'] != prot)])

                    accuracy = (TP + TN) / (TP + FP + FN + TN)
                    precision = TP / (TP + FP)
                    recall = TP / (TP + FN)
                    specificity = TN / (TN + FP)
                    F1 = 2 * (recall * precision) / (recall + precision)

                    scores.append([prot,accuracy,precision,recall,specificity,F1])

                except:
                    pass #scores.append([0,0,0,0,0,0])

            #print(scores)
            pos = 0
            elem = 0
            for i, j in enumerate(scores):
                #print(j)
                if j[5] > pos:
                    pos = j[5]
                    elem = i
                    #print(i)

            best_scores.append(scores[elem])

        vals = pd.DataFrame(best_scores, columns=
        ['Protocol', 'Accuracy', 'Precision', 'Recall', 'Specificity', 'F1 Score', ]).set_index('Protocol')
        vals = vals.round(3)
        path = path_tables + '/{}_scores_communities_{}.tex'.format(namefile,comm_alg)
        #vals.reset_index().to_latex(path, index=False)


        #make stats table
        #1) number of communities
        n_comms = str(len(all_comms)) + ' (' + str(len(comms)) + ')'
        col = pd.DataFrame([n_comms], index=['# Communities'], columns=['Avg.{}'.format(comm_alg)])
        #2) averages
        col = pd.concat([col, pd.DataFrame(vals.mean().round(4).rename('Avg.{}'.format(comm_alg)))])
        #3) NMI & accurqacy of number of communities
        NMI = normalized_mutual_info_score(vim_notna['prot_nr'].tolist(), vim_notna[comm_alg].tolist())
        #print(comm_alg,'. alt. NMI: ', ig.compare_communities(vim_notna['prot_nr'], vim_notna[comm_alg], method='NMI'))
        acc_nr = len(comms) / len(prots)
        col = pd.concat([col, pd.DataFrame([NMI], index=['NMI'], columns = ['Avg.{}'.format(comm_alg)]).round(4)])
        col = pd.concat([col, pd.DataFrame([acc_nr], index=['Nr. comm. accuracy'], columns=['Avg.{}'.format(comm_alg)]).round(4)])

        #df_avgs = pd.DataFrame()
        df_avgs = pd.concat([df_avgs, col.T])


    #df_avgs = df_avgs.round(3)
    path = path_tables + '/{}_scores_avgs.tex'.format(namefile)
    df_avgs.reset_index().to_latex(path, index=False)


#--------------- 5.4 - Centrality --------------------------------------------


def centrality(df, g, vertex_id_map, namefile):

    deg_centrality(df, vertex_id_map, namefile)

    tic = time.time()
    pr_vprop = gt.pagerank(g)
    centr_name = 'PageRank'
    pr_df = pd.DataFrame({"id": g.get_vertices(), centr_name: pr_vprop.get_array()}).sort_values(
        centr_name, ascending=False).merge(vertex_id_map)
    pr_df[centr_name] = pr_df[centr_name] / pr_df[centr_name].max()
    pr_df.to_csv(path_tables + '/{}_{}.csv'.format(namefile, centr_name))
    show_centrality_measures(centr_name, namefile)
    toc = time.time()
    #print('Time (seconds) to compute PageRank: ', round(toc - tic, 0))

    tic = time.time()
    if namefile == "defi_ca_network_pro":
        katz_vprop = gt.katz(g)
    elif namefile == "defi_ca_network":
        katz_vprop = gt.katz(g, alpha = 0.001)
    centr_name = 'Katz'
    katz_df = pd.DataFrame({"id": g.get_vertices(), centr_name: katz_vprop.get_array()}).sort_values(
        centr_name, ascending=False).merge(vertex_id_map)
    katz_df[centr_name] = katz_df[centr_name] / katz_df[centr_name].max()
    katz_df.to_csv(path_tables + '/{}_{}.csv'.format(namefile, centr_name))
    show_centrality_measures(centr_name, namefile)
    toc = time.time()
    #print('Time (seconds) to compute Katz: ', round(toc - tic, 0))


def deg_centrality(df, vertex_id_map, namefile):
    #G_ind = nx.from_pandas_edgelist(df, 'from', 'to')
    G = nx.from_pandas_edgelist(df, 'from', 'to', create_using=nx.DiGraph())

    tic = time.time()
    degc = nx.in_degree_centrality(G)
    centr_name = 'Indegree'
    degc_df = pd.DataFrame.from_dict(degc, orient='index').sort_index(
        ascending=True).reset_index().rename(columns={0: centr_name, 'index': 'id'}).sort_values(
        'Indegree', ascending=False).merge(vertex_id_map)
    degc_df[centr_name] = degc_df[centr_name] / degc_df[centr_name].max()
    degc_df.to_csv(path_tables + '/{}_{}.csv'.format(namefile, centr_name))
    show_centrality_measures(centr_name, namefile)
    toc = time.time()
    #print('Time (seconds) to compute Indegree: ', round(toc - tic, 0))


def show_centrality_measures(centr_name, namefile):
    df_c = pd.read_csv(path_tables + '/{}_{}.csv'.format(namefile, centr_name), index_col=0)

    plot_centrality(df_c, centr_name, namefile)

    table = df_c[['address', centr_name]].head(15).set_index('address')
    table = df_c[['address', centr_name]].head(15).set_index('address')

    header = ['Address', centr_name + ' centrality']

    path = path_tables + '/{}_first15by_{}.tex'.format(namefile, centr_name)

    table.reset_index().to_latex(path, index=False, header=header)


def plot_centrality(df_c, centr_name, namefile):
    fig, ax = plt.subplots()

    ax.scatter(np.arange(1, 1 + len(df_c), 1), df_c[centr_name], facecolors='none', edgecolors='b')
    ax.set_xscale('log')

    ax.set_xlabel('Vetrices, ranked in descending order')
    ax.set_ylabel('{} centrality'.format(centr_name))

    fig.savefig(path_figures + '/{}_{}.png'.format(namefile, centr_name), format='png')
    plt.close(fig)


#---------------------------------- Main --------------------------------------------

def network_analysis(namefile,block_st = 14000000, block_end = 14000999):

    if not os.path.exists(path_output):
        os.makedirs(path_output)
        os.chmod(path_output, 0o777)
    if not os.path.exists(path_figures):
        os.makedirs(path_figures)
        os.chmod(path_figures, 0o777)
    if not os.path.exists(path_tables):
        os.makedirs(path_tables)
        os.chmod(path_tables, 0o777)

    df, vertex_id_map, g = load_files(namefile,block_st,block_end)
    df_cols = pd.read_csv(path_colors + '/protocol_colors.csv', sep=';', index_col=0)

    table_metrics(df, g, namefile)

    # 5.1 powerlaw analysis
    data_for_r(g, namefile)
    tab_degrees(g, vertex_id_map, path_tables, namefile)

    # 5.2 components analysis
    components(df, g, vertex_id_map, namefile)

    # 5.3 communities
    communities(g, vertex_id_map, df_cols, namefile)

    # 5.4 centrality
    centrality(df, g, vertex_id_map, namefile)

    print(namefile, " analysis: done")

def main():

    network_analysis("defi_ca_network")
    network_analysis("defi_ca_network_pro")


if __name__ == '__main__':

    main()