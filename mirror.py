#! -*- coding: utf-8 -*-
import pymel.core as pm
import re
from itertools import chain


def divide_select_list(selected):
    """
    :param list of pm.PyNode selected: selection list
    :rtype: (list of pm.nt.Cluster, pm.nt.Mesh)
    """
    if 2 > len(selected):
        raise Exception(u'Please select clusters and mesh.')

    clusters = pm.listConnections \
        (selected[0:-1], destination=True, type=u'cluster')
    if 0 >= len(clusters):
        raise Exception(u'Please select clusters and mesh.')

    paste_mesh = selected[-1].getShape()
    if type(paste_mesh) is not pm.nodetypes.Mesh:
        raise Exception(u'Finally select the mesh.')

    return clusters, paste_mesh


class ClusterCopy(object):
    re_node_name = re.compile(r"^[^\.]+")

    def __init__(self, cluster, mesh):
        self.cluster = cluster
        self.mesh = mesh
        self.members = self._get_members()

    def select_same_members(self, dst_mesh):
        pm.select(self._get_renamed_members(dst_mesh))

    def copy(self, dst_cluster, dst_mesh):
        self._attr_copy(dst_cluster)
        self._weight_copy(dst_cluster, dst_mesh)

    def _get_members(self):
        res = []
        for s in pm.listSets(object=self.cluster):
            res.extend(s.members())
        return res

    def _get_renamed_members(self, dst_mesh):
        dst_name = dst_mesh.name()
        res = []
        for vtx in chain.from_iterable(self.members):
            renamed_vtx = ClusterCopy.re_node_name.sub(dst_name, vtx.name())
            res.append(renamed_vtx)
        return res

    def _attr_copy(self, dst_cluster):
        src = self.cluster
        dst_cluster.attr('relative') \
            .set(src.attr('relative').get())
        dst_cluster.attr('usePartialResolution') \
            .set(src.attr('usePartialResolution').get())
        dst_cluster.attr('angleInterpolation') \
            .set(src.attr('angleInterpolation').get())
        dst_cluster.attr('percentResolution') \
            .set(src.attr('percentResolution').get())
        dst_cluster.setEnvelope(src.getEnvelope())

    def _weight_copy(self, dst_cluster, dst_mesh):
        weights = pm.percent(self.cluster, self.mesh, query=True, value=True)
        for i, weight in enumerate(weights):
            pm.percent(dst_cluster, dst_mesh.vtx[i], value=weight)


def mesh2pointsDict(mesh):
    return {v: v.getPosition(space='world') for v in mesh.vtx}


def distanceMin(turn_x_point, mesh_points):
    return min(mesh_points, key=lambda k: mesh_points[k].distanceTo(turn_x_point))


def mirror_copy(cluster, mesh):
    cc = ClusterCopy(cluster, mesh)
    mesh_points = mesh2pointsDict(mesh)
    turn_x_weights = {}
    for vtx in chain.from_iterable(cc.members):
        cl_point = vtx.getPosition(space='world')
        turn_x_point = \
            pm.datatypes.Point(cl_point.x * -1, cl_point.y, cl_point.z)
        turn_x_vtx = \
            distanceMin(turn_x_point, mesh_points)
        turn_x_weights[turn_x_vtx] = \
            pm.percent(cluster, vtx, query=True, value=True)[0]
    pm.select(turn_x_weights.keys())
    new_cluster, _ = pm.cluster()
    cc.copy(new_cluster, mesh)
    for vtx in turn_x_weights:
        pm.percent(new_cluster, vtx, value=turn_x_weights[vtx])


def mirror_mesh():
    selected = pm.selected()
    clusters, paste_mesh = divide_select_list(selected)
    for cluster in clusters:
        copy_mesh = cluster.getGeometry()
        if 1 < len(copy_mesh):
            print(u'Not support multi mesh cluster({}). skipped.'.format(cluster.name))
            continue

        try:
            copy_mesh = pm.nt.Mesh(copy_mesh[0])
        except TypeError:
            print(u'Not support type not mesh cluster({}). skipped.'.format(cluster.name))
            continue

        if copy_mesh.name() == paste_mesh.name():
            mirror_copy(cluster, paste_mesh)
        else:
            cc = ClusterCopy(cluster, copy_mesh)
            cc.select_same_members(paste_mesh)
            new_cluster, _ = pm.cluster()
            cc.copy(new_cluster, paste_mesh)
