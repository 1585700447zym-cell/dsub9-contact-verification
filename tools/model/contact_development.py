"""Separate convex-hole development model; the historical analytic SDF stays intact.

The bore is circumscribed by tangent planar faces. This changes its shape by a
known sub-micron amount at 128 sectors; it is not an exact analytic SDF repair.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from tools.validation.run_contact_cases import ROOT, FORMAL_MODEL, _project_root_cwd


OUTPUT_DIR = ROOT/'deliverables/contact_coverage_repair'
MODEL_NAME = 'dsub9_convex128_contact_dev_v1'


def _resolution(segments):
    if type(segments) is not int or segments not in (32, 64, 128, 256):
        raise ValueError('segments must be one of 32, 64, 128, 256')


def radial_error(radius, segments):
    _resolution(segments)
    return radius * (1/math.cos(math.pi/segments)-1)


def sector_vertices(inner, outer, z0, z1, segments, index):
    _resolution(segments)
    if not np.isfinite([inner, outer, z0, z1]).all() or not 0 < inner < outer or not z0 < z1:
        raise ValueError('invalid sector dimensions')
    if not isinstance(index, int) or not 0 <= index < segments:
        raise ValueError('invalid sector index')
    t0, t1 = (2*math.pi*(index+v)/segments for v in (-.5, .5))
    ri, ro = inner/math.cos(math.pi/segments), outer/math.cos(math.pi/segments)
    return np.array([[r*math.cos(t), r*math.sin(t), z] for z in (z0, z1)
                     for r, t in ((ri,t0), (ro,t0), (ro,t1), (ri,t1))])


def build_xml(segments=128, ccd_tolerance=1e-9, *, file_directory=None):
    """Build a complete model referencing the unchanged project assets.

file_directory is the directory of an exported XML; None means an in-memory
XML compiled while cwd is the project root. No source assets are regenerated.
"""
    _resolution(segments)
    if not math.isfinite(ccd_tolerance) or not 0 < ccd_tolerance <= 1e-6:
        raise ValueError('invalid ccd tolerance')
    tree = ET.parse(FORMAL_MODEL).getroot()
    tree.set('model', f'dsub9_convex{segments}_contact_dev_v1')
    base = ROOT if file_directory is None else Path(file_directory)
    tree.find('compiler').set('meshdir', Path(os.path.relpath(ROOT/'assets', base)).as_posix())
    for inc in tree.findall('include'):
        original = ROOT/'models'/inc.get('file')
        inc.set('file', Path(os.path.relpath(original, base)).as_posix())
    # All original gravity, solver and geom material parameters are retained.
    # Tighten convex distance tolerance for the sub-millimetre bore geometry.
    tree.find('option').set('ccd_tolerance', format(ccd_tolerance, '.16g'))
    tree.find('option').set('timestep', '0.0002')
    params = {c.get('key'): float(c.get('value'))
              for c in tree.findall('.//extension/plugin/instance/config')}
    tree.remove(tree.find('extension'))
    for asset in tree.findall('asset'):
        for mesh in list(asset):
            if mesh.get('name') == 'hole_sdf_mesh':
                asset.remove(mesh)
    fallback_default = tree.find('.//default[@class="hole_polygon32_collision"]')
    fallback_default.set('class', 'hole_convex_collision')
    female = tree.find('.//body[@name="female"]')
    holes = [(g.get('name')[-2:], g.get('pos')) for g in female.findall('geom') if g.get('type')=='sdf']
    for g in list(female):
        if g.get('type')=='sdf':
            female.remove(g)
    assets = tree.find('asset')
    layers = [('entry', params['entry_radius'], 0., params['entry_depth']),
              ('main', params['bore_radius'], params['entry_depth'], params['bore_depth'])]
    for layer, inner, z0, z1 in layers:
        for j in range(segments):
            vertices = sector_vertices(inner, params['outer_radius'], z0, z1, segments, j)
            name = f'convex{segments}_{layer}_{j:03}'
            ET.SubElement(assets, 'mesh', name=name,
                          vertex=' '.join(format(float(v), '.16g') for v in vertices.ravel()))
            for number, pos in holes:
                ET.SubElement(female, 'geom', name=f'hole_convex{segments}_{number}_{layer}_{j:03}',
                              type='mesh', mesh=name, pos=pos, **{'class': 'hole_convex_collision'})
    ET.indent(tree, space='  ')
    return ET.tostring(tree, encoding='unicode')+'\n'


def load_model(segments=128, ccd_tolerance=1e-9):
    """Return a fresh model, so changing an option cannot contaminate a baseline."""
    xml = build_xml(segments, ccd_tolerance)
    with _project_root_cwd():
        model = mujoco.MjModel.from_xml_string(xml)
    model.opt.timestep = .0002
    return model


def export_model():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR/'dsub9_convex128_contact_dev_v1.xml'
    xml = build_xml(file_directory=OUTPUT_DIR)
    target.write_text(xml, encoding='utf-8', newline='\n')
    return target


if __name__ == '__main__':
    print(export_model())
