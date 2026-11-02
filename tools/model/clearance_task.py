"""Versioned 1.20 mm bore task; geometry-only referee, never policy input."""
import math
import xml.etree.ElementTree as ET

import numpy as np

from tools.model.contact_development import build_xml, sector_vertices
from tools.validation.run_contact_cases import FORMAL_MODEL
from tools.validation.run_b1_baseline import FINISH

TASK_ID = 'dsub9_clearance120_xy80_v1'
BORE_RADIUS_M = .0006
SEGMENTS = 256
_source = ET.parse(FORMAL_MODEL).getroot()
_pins = _source.findall('.//geom[@class="pin_collision"]')
if len(_pins) != 9:
    raise ValueError('Expected nine source pins')
_pin_centers = np.array([[float(v) for v in g.get('pos').split()] for g in _pins])
_pin_sizes = np.array([[float(v) for v in g.get('size').split()] for g in _pins])
if not np.allclose(_pin_sizes, [.0005, .002], rtol=0, atol=1e-15):
    raise ValueError('Task requires 1 mm diameter, 4 mm long source pins')


def finish_criteria():
    return {**FINISH, 'xy_tolerance_m': 80e-6}


def build_task_xml(file_directory=None):
    tree = ET.fromstring(build_xml(SEGMENTS, 1e-12, file_directory=file_directory))
    tree.set('model', TASK_ID)
    for j in range(SEGMENTS):
        mesh = tree.find(f'.//mesh[@name="convex256_main_{j:03}"]')
        vertices = sector_vertices(BORE_RADIUS_M, .001, .00025, .0045, SEGMENTS, j)
        mesh.set('vertex', ' '.join(format(float(v), '.16g') for v in vertices.ravel()))
    # The original visual mesh has narrower holes. Show the actual collision
    # surfaces instead; old CAD/visual assets remain unchanged on disk.
    female = tree.find('.//body[@name="female"]')
    female.remove(female.find('geom[@name="female_visual"]'))
    for geom in female.findall('geom'):
        geom.set('group', '2')
        geom.set('rgba', '0.65 0.72 0.8 1')
    ET.indent(tree, space='  ')
    return ET.tostring(tree, encoding='unicode') + '\n'


def pin_clearance_m(row):
    """Conservative full-shaft fit in the circular main bore at a saved pose.

    Bounds projected cylinder radius by its physical radius, and the center
    line by its two endpoints. This sufficient condition also checks the short
    shaft segment in the wider entrance against the narrower main bore, so can
    reject a marginal physically possible pose. It never adds simulation steps.
    """
    p = np.asarray(row['position_m'], dtype=float)
    q = np.asarray(row['quaternion_wxyz'], dtype=float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all() or not np.any(q):
        return -math.inf
    q = q / np.max(np.abs(q)); q = q / np.linalg.norm(q)
    w, x, y, z = q
    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    centers = _pin_centers @ rotation.T + p
    ends = centers[:, None, :] + np.array([-1., 1.])[None, :, None] * _pin_sizes[:, 1, None, None] * rotation[:, 2]
    offsets = ends[:, :, :2] - _pin_centers[:, None, :2]
    bound = np.linalg.norm(offsets, axis=2).max(axis=1) + _pin_sizes[:, 0]
    return float(np.min(BORE_RADIUS_M - bound))


def pin_fit(row):
    return pin_clearance_m(row) >= -1e-9
