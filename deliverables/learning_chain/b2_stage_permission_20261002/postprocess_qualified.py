"""Run the sealed report with its qualified imports and no simulation/learning."""
import time
import paired_contract as C


def main():
    from run_pair import select_runtime
    select_runtime()
    import mujoco
    import torch
    calls = dict(physics=0, model_forward=0, optimizer=0)

    def forbid(kind):
        def fail(*args, **kwargs):
            calls[kind] += 1
            raise RuntimeError('Postprocessing forbids ' + kind)
        return fail

    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_resetData', 'mj_resetDataKeyframe'):
        setattr(mujoco, name, forbid('physics'))
    torch.nn.Module._call_impl = forbid('model_forward')
    torch.optim.Adam.step = forbid('optimizer')
    import report_result
    started = time.perf_counter()
    error = None
    try:
        report_result.main()
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        C.write(C.HERE / 'result_analysis/postprocess_execution.json', dict(
            version='qualified_postprocessing_v1', elapsed_s=time.perf_counter() - started,
            error=error, calls=calls, sealed_report_sha256=C.digest(C.HERE / 'report_result.py'),
            prior_failure='Direct report invocation lacked the qualified MuJoCo import path',
            experiment_restarted=False))


if __name__ == '__main__':
    main()
