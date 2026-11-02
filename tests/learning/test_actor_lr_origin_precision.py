import numpy as np
import pytest


def check(requests, archived):
    from tools.learning import actor_lr_origin
    if not hasattr(actor_lr_origin, 'verify_warmup_requests'):
        pytest.fail('Strict warmup request comparison missing')
    actor_lr_origin.verify_warmup_requests(requests, archived)


def test_exact_float32_requests_match_archived_json_numbers():
    requests = np.array([[.25, -.75, 0., 1.]],dtype=np.float32)
    check(requests, requests.astype(np.float64).tolist())


def test_rounding_collision_does_not_hide_archived_number_difference():
    requests = np.array([[.25, -.75, 0., 1.]],dtype=np.float32)
    archived = requests.astype(np.float64)
    archived[0,0] = np.nextafter(archived[0,0], 1.)
    assert np.array_equal(requests, archived.astype(np.float32))
    with pytest.raises(ValueError, match='requests'):
        check(requests, archived.tolist())


@pytest.mark.parametrize('archived', [[[.25, -.75, float('nan'), 1.]], [[.25, -.75, 0.]]])
def test_nonfinite_or_wrong_shape_requests_rejected(archived):
    with pytest.raises(ValueError, match='requests'):
        check(np.array([[.25,-.75,0.,1.]],dtype=np.float32), archived)
