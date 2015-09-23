#! -*- coding: utf-8 -*-
import sys
import pymel.core as pm
import maya.OpenMaya as OpenMaya


def vtx2pointsDict(vtx):
    return {v: v.getPosition(space='world') for v in vtx}


def pt2pointsDict(pt):
    xform = pm.xform
    point = pm.dt.Point
    return {p: point(xform(p, query=True, translation=True, worldSpace=True))
            for p in pt}


def distanceMin(turn_x_point, points):
    return min(points, key=lambda k: points[k].distanceTo(turn_x_point))


def mirror_cluster_on_lattice():
    selected = pm.selected()
    # 選択しているノードの子孫から clusterHandle をリストアップする
    target_cluster_handles = pm.ls(selection=True,
                                   dagObjects=True,
                                   type=u'clusterHandle')

    # clusterHandle を選択していなければ終了
    assert 0 != len(target_cluster_handles), \
        u'Not find clusterHandle from selection, ' \
        u'Please select one or more clusterHandle'

    # clusterHandle のコネクションを追って cluster をリストアップする
    target_clusters = pm.listConnections(target_cluster_handles,
                                         destination=True,
                                         type=u'cluster')

    # いったん無効化するデフォーマのセットを格納する変数を宣言
    deformers = set()

    # mesh か lattice 以外を対象にしている cluster があれば格納する
    ignore_deformers = []

    for target_cluster in target_clusters:
        # cluster のデフォーム対象を getGeometry で取得: 名前の配列が返る
        output_geometries = target_cluster.getGeometry()

        # type を調べるために一度 PyNode にする
        output_geometries = [pm.PyNode(g) for g in output_geometries]

        # フィルタリングする前の数を保存
        output_num = len(output_geometries)

        # デフォーム対象を mesh か lattice だけにする
        output_geometries = filter(lambda g:
                                   pm.nodetypes.Mesh == type(g) or
                                   pm.nodetypes.Lattice == type(g),
                                   output_geometries)

        # mesh か lattice 以外にもセットされてる cluster ならスキップする
        if output_num is not len(output_geometries):
            ignore_deformers.append(target_cluster)
            continue

        # デフォーム対象のヒストリをリストアップする
        histories = pm.listHistory(output_geometries)

        # 継承している nodeType を調べて geometryFilter が含まれていたらデフォーマと確定
        [deformers.add(d)
         for d in histories
         if u'geometryFilter' in pm.nodeType(d, inherited=True)]

    # mesh か lattice 以外にアタッチしている cluster があれば選択して処理を止める
    if 0 < len(ignore_deformers):
        ignore_handles = [d.matrix.listConnections()[0] for d in ignore_deformers]
        pm.select(ignore_handles)
        ignore_names = [c.name() for c in ignore_handles]
        message = u'These are the cluster that are not supported. ' \
                  u'It must be attached only to the mesh or lattice. ' \
                  + ' '.join(ignore_names)
        OpenMaya.MGlobal.displayError(message)
        sys.exit()

    # あとで復元する envelope を保存。デフォーマをキーにしつつ envelope を保存する
    envelopes = {d: d.getEnvelope() for d in deformers}

    # デフォーマを無効化し元の形状にする
    [d.setEnvelope(0) for d in deformers]

    for target_cluster in target_clusters:
        members = []
        [members.extend(x) for x in pm.listSets(object=target_cluster)]
        members = pm.ls(members, flatten=True)
        member_dict = {}
        all_points_dict = {}
        for member in members:
            node = member.node()
            if node in member_dict:
                member_dict[node].append(member)
                continue

            member_dict[node] = [member]
            if pm.nt.Mesh == type(node):
                all_points_dict[node] = vtx2pointsDict(node.vtx)
            elif pm.nt.Lattice == type(node):
                all_points_dict[node] = pt2pointsDict(node.pt)

        weights = {}
        for node in member_dict.iterkeys():
            all_points = all_points_dict[node]
            if pm.nt.Mesh == type(node):
                for member in member_dict[node]:
                    p = member.getPosition(space='world')
                    p = pm.dt.Point(p.x * -1, p.y, p.z)
                    v = distanceMin(p, all_points)
                    weights[v] = pm.percent(target_cluster,
                                            member,
                                            query=True,
                                            value=True)[0]
            elif pm.nt.Lattice == type(node):
                xform = pm.xform
                point = pm.dt.Point
                for member in member_dict[node]:
                    p = xform(member,
                              query=True,
                              translation=True,
                              worldSpace=True)
                    p = point(p[0] * -1, p[1], p[2])
                    v = distanceMin(p, all_points)
                    weights[v] = pm.percent(target_cluster,
                                            member,
                                            query=True,
                                            value=True)[0]
        pm.select(weights.keys())
        new_cluster, new_cluster_handle = pm.cluster()

        new_cluster.attr('relative') \
            .set(target_cluster.attr('relative').get())
        new_cluster.attr('usePartialResolution') \
            .set(target_cluster.attr('usePartialResolution').get())
        new_cluster.attr('angleInterpolation') \
            .set(target_cluster.attr('angleInterpolation').get())
        new_cluster.attr('percentResolution') \
            .set(target_cluster.attr('percentResolution').get())
        new_cluster.setEnvelope(envelopes[target_cluster])

        selected.append(new_cluster_handle)

    # envelope を復元
    [d.setEnvelope(envelopes[d]) for d in envelopes.iterkeys()]

    pm.select(selected)
