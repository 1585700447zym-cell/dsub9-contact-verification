"""Recompute the new real counterexample without stepping or publishing data."""
from pathlib import Path
import gzip,json,math
import numpy as np
from tools.learning.v4_pilot_contract import read,sha,canonical
from tools.learning.v4_continuation import predict_next_search
from tools.control.search_recovery import SearchConfig
OUT=Path(__file__).resolve().parent
rawpath=OUT/'run/warmup_S50_y_neg_150.json.gz';d=json.loads(gzip.decompress(rawpath.read_bytes()))
event=d['reference_problems'][0];t=event['time_s'];i=next(i for i,r in enumerate(d['trace'][:-1]) if abs(r['time_s']-t)<1e-9)
prev=d['transitions'][i-1]['action_log'];earlier=d['transitions'][i-2]['action_log'];c=SearchConfig(**read(OUT/'configuration.json')['common']['b2_config'])
recomputed=predict_next_search(prev['predicted_reference_xy_m'],prev['predicted_limited_command'][:2],prev['next_search_theta_rad'],c,.002)
assert np.allclose(recomputed['predicted_reference_xy_m'],event['predicted_reference_xy_m'],rtol=0,atol=1e-15)
assert recomputed['reference_feasible'] is False and prev['baseline_next_zero_reference_feasible'] is False
assert prev['continuation_filter_fraction']==0. and earlier['next_zero_reference_feasible'] is True
assert np.allclose(earlier['next_zero_predicted_reference_xy_m'],prev['predicted_reference_xy_m'],rtol=0,atol=1e-15)
assert np.allclose(earlier['next_zero_limited_xy_m_s'],prev['predicted_limited_command'][:2],rtol=0,atol=1e-15)
point=np.asarray(event['reference_xy_m']);future=np.asarray(event['predicted_reference_xy_m'])
result=dict(scope='read_only_real_counterexample_no_physics_no_training',archive_sha256=sha(rawpath),event=event,
    preceding_command_time_s=d['trace'][i-1]['time_s'],preceding_request=prev['raw_action'],
    preceding_filter_fraction=prev['reference_filter_fraction'],preceding_continuation_fraction=prev['continuation_filter_fraction'],
    preceding_baseline_next_zero_feasible=prev['baseline_next_zero_reference_feasible'],recomputed_next_zero=recomputed,
    current_reference_radius_um=float(np.linalg.norm(point))*1e6,predicted_reference_radius_um=float(np.linalg.norm(future))*1e6,
    predicted_excess_nm=float(np.linalg.norm(future)-.00012)*1e9,
    prior_lookahead_matches_actual_next_zero=True,prediction_error_m=float(np.max(np.abs(np.asarray(recomputed['predicted_reference_xy_m'])-future))),
    explanation='有限一零步检查预测正确，但下一状态的零残差基线再下一步已不可行；滤波归零仍返回该基线，随后控制器按预测触发SEARCH_REFERENCE_LIMIT。不是本例预测计算偏差，也不是训练后失效。',
    formal_updates=0,policy_calls=0,new_dynamic_episodes=0,reference_actual_outside=False,
    next_proposal='为共同SEARCH基线定义边界可行性回退：接近不可继续状态时，提前制动/投影或按受控搜索结束进入既有恢复；不能只把残差归零。用本反例离线重放参考和加速度，再为B2/F/S重登记有限共同动态；不改成功/力保护，不补本轮26/4000余量。')
(OUT/'reference_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'诊断与下一步.md').write_text(f'''# 本轮新问题及最小下一方案

S负Y在{t:.3f}s触发SEARCH_REFERENCE_LIMIT。此前{result['preceding_command_time_s']:.3f}s残差过滤已降为0，日志明确指出零残差基线的下一零动作不可行。真实参考半径{result['current_reference_radius_um']:.9f}μm，下一B2预测{result['predicted_reference_radius_um']:.9f}μm，超限{result['predicted_excess_nm']:.6f}nm。

独立重算与真实事件预测的最大差{result['prediction_error_m']:.3g}m；再前一周期的一零步预测与实际下一零命令/参考逐值一致。说明预测没有在本例算错；有限安全检查不能保证每次落到“再下一零步也可继续”的状态。当前回退仅沿B2基线到本次残差候选压缩，基线本身不可继续时归零也无效。

正式更新/策略调用都是0，因此不是学习率、critic过估计或已训练actor导致的失效证据。F的随机预热成功也不能当学习收益。两回合都仿真有效、停稳、无硬保护；S因共同参考错误拒绝入池，整轮停止正确，余26动态/4000批关闭。

下一方案优先补共同SEARCH边界处理：若继续跟踪会耗尽可行性，就提前制动/投影或受控结束当前搜索、进入既有恢复。F/S/B2应共享同一规则并重评；单改S的评价/错误分类会破坏公平性。不能再只归零残差，也不能用增大学习率或降低力保护来掩盖该问题。

先用此真实反例和旧零残差轨迹离线验证参考边界、速度/加速度与受控转移，再登记少量新动态核验。是否需要更长有限前视或微小内侧余量，应由可行性重算决定，不先随意承诺数值或无限未来安全。未实施新控制方案，没有补跑训练。

[机器重算](reference_diagnosis.json)、[原始S回合](run/warmup_S50_y_neg_150.json.gz)、[实际账本](run/ledger.json)。
''',encoding='utf8')
print(canonical({k:result[k] for k in ('current_reference_radius_um','predicted_reference_radius_um','predicted_excess_nm','prediction_error_m','explanation')}))
