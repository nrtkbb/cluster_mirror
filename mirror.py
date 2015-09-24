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
    # 最後に選択を復元するために保存する
    selected = pm.selected()

    # 選択しているノードから clusterHandle をリストアップする
    target_cluster_handles = pm.ls(selection=True, type=u'clusterHandle')

    # 選択している transform の shape を確認して clusterHandle なら格納する
    is_cluster_only = True
    for transform in pm.ls(selection=True, type=u'transform'):
        for shape in transform.getShapes():
            if pm.nt.ClusterHandle == type(shape):
                target_cluster_handles.append(shape)
            else:
                is_cluster_only = False

    # 初めに選択していたリストと数が合わなかったら
    # clusterHandle 以外を選択していたとみなして終了
    if is_cluster_only and len(selected) == len(target_cluster_handles):
        message = u'These are not clusterHandle. ' \
                  u'Please select the clusterHandle only.'
        OpenMaya.MGlobal.displayError(message)
        sys.exit()

    # clusterHandle を一つも選択していなければ終了
    if 0 == len(target_cluster_handles):
        message = u'Not found clusterHandle from selection list, ' \
                  u'Please select more clusterHandle before execute.'
        OpenMaya.MGlobal.displayError(message)
        sys.exit()

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
        message = u'These are the cluster that are not supported. ' \
                  u'It must be attached only to the mesh or lattice. => ' \
                  + ' '.join([c.name() for c in ignore_handles])
        OpenMaya.MGlobal.displayError(message)
        sys.exit()

    # あとで復元する envelope を保存。デフォーマをキーにしつつ envelope を保存する
    envelopes = {d: d.getEnvelope() for d in deformers}

    # デフォーマを無効化し元の形状にする
    [d.setEnvelope(0) for d in deformers]

    for target_cluster in target_clusters:

        # target_cluster のデフォーム対象を格納する
        members = []
        [members.extend(x) for x in pm.listSets(object=target_cluster)]

        # lattice1.pt[0:9][0:9][0:9] みたいにまとめられてる配列を全部バラバラに扱う
        members = pm.ls(members, flatten=True)

        # node をキーにして ポイント を値に格納する
        member_dict = {}

        # node の全ポイントの座標を pm.dt.Point 型で格納する
        all_points_dict = {}

        for member in members:
            # ポイントの node 部分を摘出する
            node = member.node()

            # すでに node がキーに存在するなら
            if node in member_dict:
                # ポイントを格納して次へ進む
                member_dict[node].append(member)
                continue

            # ポイントを list でラッピングして値を初期化
            member_dict[node] = [member]

            # さらに mesh や lattice の全ポイント座標を格納する
            if pm.nt.Mesh == type(node):
                all_points_dict[node] = vtx2pointsDict(node.vtx)
            elif pm.nt.Lattice == type(node):
                all_points_dict[node] = pt2pointsDict(node.pt)

        mirror_point_and_weights = {}
        for node in member_dict.iterkeys():
            all_points = all_points_dict[node]
            if pm.nt.Mesh == type(node):
                for member in member_dict[node]:
                    # vtx の world 座標を取得する。pm.dt.Point 型で返ってくる
                    p = member.getPosition(space='world')

                    # x を反転して
                    p = pm.dt.Point(p.x * -1, p.y, p.z)

                    # p に一番近いポイントを摘出
                    v = distanceMin(p, all_points)

                    # member のウェイトをコピーするため、保存している
                    mirror_point_and_weights[v] = pm.percent(target_cluster,
                                                             member,
                                                             query=True,
                                                             value=True)[0]
            elif pm.nt.Lattice == type(node):

                # ここでは負荷軽減のため . （ドットシンタックス）無しで、
                # 関数を呼び出せるようにキャッシュしている
                xform = pm.xform
                point = pm.dt.Point
                for member in member_dict[node]:
                    # pt の world 座標を取得する。list of double 型で返ってくる
                    p = xform(member,
                              query=True,
                              translation=True,
                              worldSpace=True)

                    # x を反転しつつ pm.dt.Point 型にする
                    p = point(p[0] * -1, p[1], p[2])

                    # p に一番近いポイントを摘出
                    v = distanceMin(p, all_points)

                    # member のウェイトをコピーするため、保存している
                    mirror_point_and_weights[v] = pm.percent(target_cluster,
                                                             member,
                                                             query=True,
                                                             value=True)[0]
        # 反転した点を選択する
        pm.select(mirror_point_and_weights.keys())

        # cluster を作成する
        new_cluster, new_cluster_handle = pm.cluster()

        # 新しい cluster に元のアトリビュートの値をセットする
        new_cluster.attr('relative') \
            .set(target_cluster.attr('relative').get())
        new_cluster.attr('usePartialResolution') \
            .set(target_cluster.attr('usePartialResolution').get())
        new_cluster.attr('angleInterpolation') \
            .set(target_cluster.attr('angleInterpolation').get())
        new_cluster.attr('percentResolution') \
            .set(target_cluster.attr('percentResolution').get())
        new_cluster.setEnvelope(envelopes[target_cluster])

        # 処理が完了した時に選択するリストに新しい clusterHandle も含める
        selected.append(new_cluster_handle)

    # envelope を復元
    [d.setEnvelope(envelopes[d]) for d in envelopes.iterkeys()]

    # 初めに選択していたリスト + 新たな clusterHandle リストを選択する
    pm.select(selected)
