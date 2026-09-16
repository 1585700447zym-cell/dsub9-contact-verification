// Copy into the private .build directory before running, to use its runtime node_modules link.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile,FileBlob} from '@oai/artifact-tool';

const root=process.cwd();
const out=path.join(root,'deliverables/monthly_progress/2026-09');
const build=path.join(out,'.build');
const validationDir=path.join(root,'tmp/monthly_progress_validation');
await fs.mkdir(validationDir,{recursive:true});
const evidence=path.join(root,'deliverables/b1_fixed_admittance');
const SKILL='C:/Users/ok everything/.codex/plugins/cache/openai-primary-runtime/presentations/26.905.11957/skills/presentations';
const PYTHON='C:/Users/ok everything/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
process.env.RUNTIME_NODE_MODULES='C:/Users/ok everything/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const template='C:/Users/ok everything/.codex/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/artifact-template-simple-light-mode/assets/reference.pptx';
const {finalizePresentation,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const facts=JSON.parse(await fs.readFile(path.join(evidence,'monthly_facts.json'),'utf8'));
const index=JSON.parse(await fs.readFile(path.join(evidence,'results_index.json'),'utf8'));
const pair=await Promise.all([8,9].map(async i=>JSON.parse(await fs.readFile(path.join(evidence,index.runs[i].file),'utf8'))));
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
for(const [file,digest] of Object.entries(facts.source_files)){
 if(sha(await fs.readFile(path.join(evidence,file)))!==digest)throw new Error('Monthly source changed: '+file);
}
const imported=await PresentationFile.importPptx(await FileBlob.load(template));
const proto=imported.toProto();
const selected=[1,17,8,22,21,5];
proto.slides=selected.map((n,i)=>({...proto.slides[n-1],index:i}));
// The retained chart frames host new literal data. Remove only the old sample charts.
for(const i of [3,4])proto.slides[i].elements=proto.slides[i].elements.filter(e=>e.name!=='Chart 2');
// Slide 22's template chart border would intersect the larger native chart we need.
proto.slides[3].elements=proto.slides[3].elements.filter(e=>e.id!=='2');
const p=Presentation.load(proto);
const font='Microsoft YaHei';
const s=p.slides.items;
function shape(sl,id){const found=sl.shapes.items.find(x=>x.id===String(id));if(!found)throw new Error('Missing shape '+id);return found;}
function edit(sl,id,text,size,position){const sh=shape(sl,id);sh.text=text;sh.text.style={typeface:font,fontSize:size,color:'#171717',autoFit:'none'};if(position)sh.position=position;return sh;}
function title(sl,id,text){edit(sl,id,text,32,{left:41.33,top:36.12,width:1197.33,height:110});}
function note(sl,text){sl.speakerNotes.textFrame.setText(text);}
function footer(sl,id,n){edit(sl,id,String(n),12,{left:1184.18,top:659.24,width:54.48,height:25.33});}

edit(s[0],4,'D-sub9 装配\n阶段进展',96);
edit(s[0],5,'接触驱动仿真与固定导纳基线\n截至 2026 年 9 月 16 日',24);
edit(s[0],6,'课题月度汇报',24);
note(s[0],'本文件为截至 2026-09-16 的阶段快照，不代表整月最终总结。来源：deliverables/b1_fixed_admittance/B1固定导纳_开发报告.md。');

title(s[1],11,'本阶段完成的工作');footer(s[1],4,2);
edit(s[1],9,'已完成',18);edit(s[1],13,'已完成',18);edit(s[1],14,'本次完成',18);
edit(s[1],15,'接触模型\n识别针孔和壳体接触\n检查漏检与几何近似',24);
edit(s[1],8,'动态执行\n接触反力影响实际运动\n实现限速与受限停止',24);
edit(s[1],19,'固定导纳 B1\n闭环修正位置和姿态\n完成 7 个工况的对照',24);
// Keep the template timeline within its actual page, correcting its inherited overhang.
shape(s[1],2).position={left:35.46,top:354.20,width:1203.2,height:.032};
note(s[1],'来源：contact_coverage_repair/coverage_results.json；dynamic_actuator_v1/dynamic_results.json；b1_fixed_admittance/results_index.json。动态阶段旧开发门槛未全部通过，原失败记录保留。这里的“完成”指实现与限定开发实验，不是全域有效性验收。');

title(s[2],533,'接触反馈与固定导纳');footer(s[2],532,3);
edit(s[2],8,'接触载荷驱动修正\n\n读取接触力与力矩\n计算 XY 和倾角修正速度\n经限幅与保护执行运动\n\nZ 方向保持受限推进\n当前尚无学习或主动搜索',24);
const sourceImage=await fs.readFile(path.join(evidence,'replay/B1终态_全阵列.png'));
const modelImage=s[2].images.items[0];modelImage.replace({blob:sourceImage,contentType:'image/png',fit:'contain',alt:'由 B1 实际积分终态渲染的 D-sub9 全阵列'});
modelImage.frame={left:658.17,top:150,width:581.6,height:479.76};
note(s[2],'图为 combined_a_scale_0.75_b1.json 中最终实际位姿的 MuJoCo 回放，透明材质只用于显示。B1 输入为 M 原点世界坐标接触 Fx、Fy、Tx、Ty，不读取真实针孔误差。当前模型不含完整 CR5 和手指柔性。');

title(s[3],11,'全部开发工况的推进对照');footer(s[3],4,4);
edit(s[3],6,'14 个配对回合\n相同初始条件、推进速度和保护\n固定参数，中途不调整\n几何完成均为同轴无接触工况',24);
edit(s[3],38,String(facts.successful_cases[0].length),64);
edit(s[3],39,'零反馈参考\n几何完成工况数',24);
edit(s[3],41,String(facts.successful_cases[1].length),64);
edit(s[3],42,'B1 固定导纳\n几何完成工况数',24);
const bar=s[3].charts.add('bar',{
 position:{left:41.33,top:155,width:595,height:474},
 categories:['同轴','X偏差','Y偏差','倾角','A×0.75','B×0.75','A全幅'],
 series:[{name:'零反馈',values:facts.advance_mm[0].map(v=>Number(v.toFixed(6))),fill:'#778391'},
         {name:'B1',values:facts.advance_mm[1].map(v=>Number(v.toFixed(6))),fill:'#18799C'}],
 barOptions:{direction:'column',grouping:'clustered'},hasLegend:true,
 legend:{position:'top',textStyle:{fontSize:18}},
 xAxis:{textStyle:{fontSize:16},title:'7 个固定开发工况'},
 yAxis:{min:0,max:4.5,majorUnit:1,title:{text:'最终实际推进 / mm',textStyle:{fontSize:18}},textStyle:{fontSize:16},numberFormatCode:'0.0'},
 dataLabels:{showValue:false},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF'
});applyPresentationChartFont(bar,{fontFamily:font});
note(s[3],facts.experiment_summary+' 名义目标推进量 4 mm。图表数据以 mm 为单位保留 6 位小数，以支持可编辑工作簿；全部原始精度数值见 results_index.json 和 monthly_facts.json。该固定样本计数不是统计成功率；同轴无接触完成不能证明导纳有效。几何完成还检查位置、总姿态、低速保持与全回合载荷。');

title(s[4],11,'联合偏差的局部推进结果');footer(s[4],4,5);
edit(s[4],43,'联合 A ×0.75\n初始位置偏差 +45 / −30 μm\n初始倾角 +1.125 / −1.125°',24,{left:657.33,top:170,width:581.6,height:153});
edit(s[4],38,facts.advance_mm[0][4].toFixed(3),49);
edit(s[4],39,'零反馈推进 / mm\n'+facts.records[8].termination_zh,23);
edit(s[4],41,facts.advance_mm[1][4].toFixed(3),49);
edit(s[4],42,'B1 推进 / mm\n'+facts.records[9].termination_zh,23);
const end=Math.max(...pair.map(r=>r.trace.at(-1).time_s));
const sample=Array.from({length:15},(_,i)=>end*i/14);
const sampled=pair.map(r=>sample.map(t=>{
 const row=r.trace.findLast(x=>x.time_s<=t);
 return Number(((row.position_m[2]-r.case.start_origin_z_m)*1000).toFixed(6));
}));
const line=s[4].charts.add('line',{
 position:{left:41.33,top:152,width:581.02,height:477},categories:sample.map(x=>x.toFixed(1)),
 series:[{name:'零反馈',values:sampled[0],line:{fill:'#778391',width:2}},{name:'B1',values:sampled[1],line:{fill:'#18799C',width:2}}],
 lineOptions:{smooth:false},
 hasLegend:true,legend:{position:'top',textStyle:{fontSize:18}},
 xAxis:{title:'仿真时间 / s',textStyle:{fontSize:14}},
 yAxis:{title:{text:'实际推进 / mm',textStyle:{fontSize:18}},textStyle:{fontSize:16},min:0,max:.30,numberFormatCode:'0.00'},
 dataLabels:{showValue:false},chartFill:'#FFFFFF',plotAreaFill:'#FFFFFF'
});applyPresentationChartFont(line,{fontFamily:font});
note(s[4],facts.improvement_statement+' 两者均未在该工况完成插入。曲线以记录采样，较短回合结束后保持其末值，仅便于共同时间轴展示。完整连续控制周期曲线及力与姿态见 01_B1与零反馈对照.png。该代表工况预先选定。');

title(s[5],533,'当前限制与下一步');footer(s[5],532,6);
edit(s[5],7,'当前限制\n\n部分偏差仍在入口台阶受阻\n孔离散精度影响部分接触结果\n夹持和接触参数尚未实物标定\n当前结果限于固定开发工况',26);
edit(s[5],8,'下一步：B2 搜索与恢复\n\n先处理 B1 已暴露的停滞工况\n设置搜索范围、回撤和重试预算\n冻结评价条件后再引入残差学习\n保留过程曲线与失败样本',26);
note(s[5],facts.limitations.join('\n')+'\n'+facts.next_steps.join('\n')+'\n原动态门槛失败不会被此次基线结果覆盖。论文贡献需要后续算法对照和独立测试支撑，不能把模型精细度或模块数量当作创新。');

await fs.mkdir(build,{recursive:true});
const draft=path.join(build,'candidate.pptx');
await (await PresentationFile.exportPptx(p)).save(draft);
const finalPath=path.join(out,process.argv[2]||'课题月度进展_2026-09-16.pptx');
const result=await finalizePresentation({workspaceDir:root,candidatePath:draft,finalPath,
 pythonExecutable:PYTHON,
 integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
 explicitTotalSlideCount:6,requiredNativeChartOwnerSlides:[4,5],materializeLiteralChartWorkbooks:true,
 // Chinese adaptation supplements the retained theme with an installed Chinese font.
 fontPolicy:{basis:'design',families:['Helvetica Neue',font],scriptFonts:{ea:font}},verifyArtifactToolImport:true,
 receiptPath:path.join(validationDir,path.basename(finalPath)+'.validation.json')});
console.log(JSON.stringify(result));
const final=await PresentationFile.importPptx(await FileBlob.load(finalPath));
const preview=path.join(out,'slides');await fs.mkdir(preview,{recursive:true});
for(let i=0;i<final.slides.items.length;i++){
 const png=await final.slides.items[i].export({format:'png',scale:1});
 await fs.writeFile(path.join(preview,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
await fs.writeFile(path.join(build,'final.inspect.ndjson'),(await final.inspect({kind:'slide,textbox,chart',maxChars:150000})).ndjson);
const script=`# 月度进展汇报讲稿（截至 2026-09-16）\n\n本阶段的主要进展是建立了接触影响实际运动的仿真，并接入固定导纳 B1 控制。针孔几何模型能够产生接触力，控制器据此修正横向位置和倾角，Z 方向保持受限推进。当前使用的是简化的笛卡尔动态执行器，还没有完整复现 CR5 和真实夹爪。\n\n${facts.experiment_summary} 这些都是固定开发工况，不能解释为总体成功率。两种控制使用相同底层驱动与保护条件。同轴无接触工况得到相同结果，因此它只说明自由运动流程可用。\n\n${facts.improvement_statement} 该联合偏差下两种方法都还没有完成插入。另一方面，单独横向偏差下，固定导纳仍可能停在入口台阶附近。这说明固定反馈有明确局限，也给后续策略留下了可复查的对照基线。\n\n下一步先实现带范围和重试预算的 B2 搜索与恢复，检查能否解除这些停滞。在评价条件冻结后，再引入四维残差学习并开展独立测试。真实夹持关系、力传感器噪声和接触参数还需要实物标定。\n\n汇报时可以播放真实轨迹 GIF，并配合全工况推进图说明结果。当前阶段不能宣称实机成功率、泛化性能或论文创新已经得到验证。\n`;
await fs.writeFile(path.join(out,'一页汇报讲稿.md'),script,'utf8');
await fs.writeFile(path.join(out,'素材使用说明.md'),`# 2026 年 9 月阶段汇报素材\n\n这是截至 2026-09-16 的阶段快照。PPT 中正文、数值与两张图表可编辑，模型图来自实际记录的位姿。\n\n- slides/：逐页 PNG。\n- 一页汇报讲稿.md：可直接参考的讲述顺序。\n- ../../b1_fixed_admittance/：原始回合、完整科学曲线与真实轨迹回放。\n\nPPT 曲线采样用于展示，较短回合结束后保持末值。精确峰值和终止原因以开发报告与 JSON 记录为准。不要把固定工况计数称为统计成功率，也不要把局部推进称为完整插装成功。\n\n模板：Simple Light Mode，保留源版式并补充中文字体。原模板未修改。\n`,'utf8');
await fs.writeFile(path.join(out,'sources.json'),JSON.stringify({as_of:facts.as_of,template,selected_template_slides:selected,
 template_sha256:sha(await fs.readFile(template)),facts_sha256:sha(await fs.readFile(path.join(evidence,'monthly_facts.json'))),
 source_runs:facts.source_files,deck_sha256:sha(await fs.readFile(finalPath)),builder_sha256:sha(await fs.readFile(path.join(root,'tools/reporting/build_monthly_progress.mjs')))},null,2)+'\n');
console.log(finalPath);
