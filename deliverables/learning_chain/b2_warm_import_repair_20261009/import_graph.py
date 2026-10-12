"""Source-level import closure of repository modules; never execute inspected source.

External packages are named, not imported or recursively analyzed. Function-local
imports are recorded separately. This is not a Python interpreter or a numerical
runtime qualification; the live NoPhysics finder remains authoritative at runtime.
"""
import ast,hashlib
from pathlib import Path

def collect_graph(root,local,entries):
    root=Path(root).resolve();local=Path(local).resolve()
    modules={};namespaces={};eager=[];deferred=[];external=set();dynamic_deferred=[];queue=[]
    def resolve(name):
        if not name or any(not p.isidentifier() for p in name.split('.')):raise ValueError('Invalid module '+name)
        base=root if name=='tools' or name.startswith('tools.') else local
        stem=base.joinpath(*name.split('.'))
        if stem.with_suffix('.py').is_file():return stem.with_suffix('.py')
        if (stem/'__init__.py').is_file():return stem/'__init__.py'
        if stem.is_dir():return stem
        return None
    def request(source,target,line,kind='import'):
        eager.append(dict(source=source,target=target,line=line,kind=kind))
        path=resolve(target)
        if path is None:
            if target=='tools' or target.startswith('tools.'):raise ValueError('Missing repository module '+target)
            external.add(target);return
        for i in range(1,len(target.split('.'))):
            parent='.'.join(target.split('.')[:i]);parent_path=resolve(parent)
            if parent_path is not None:
                eager.append(dict(source=source,target=parent,line=line,kind='parent_initialization'))
                queue.append((parent,parent_path))
        queue.append((target,path))
    for entry in entries:
        path=resolve(entry)
        if path is None or path.is_dir():raise ValueError('Entry source missing '+entry)
        request('<entry>',entry,0,'entry')
    while queue:
        name,path=queue.pop(0)
        if name in modules or name in namespaces:continue
        if path.is_dir():namespaces[name]=str(path);continue
        data=path.read_bytes();tree=ast.parse(data.decode('utf8'),filename=str(path))
        modules[name]=dict(path=str(path),sha256=hashlib.sha256(data).hexdigest())
        package=name if path.name=='__init__.py' else name.rpartition('.')[0]
        aliases={'__import__':'__import__'}
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):
                for a in n.names:
                    if a.name=='importlib':aliases[a.asname or a.name]='importlib'
            elif isinstance(n,ast.ImportFrom) and n.module=='importlib':
                for a in n.names:
                    if a.name=='import_module':aliases[a.asname or a.name]='importlib.import_module'
        def absolute(module,level):
            if not level:return module or ''
            parts=package.split('.') if package else []
            if level>len(parts):raise ValueError('Relative import escapes '+name)
            return '.'.join(parts[:len(parts)-level+1]+([module] if module else []))
        def record(target,node,lazy,kind='import'):
            if lazy:deferred.append(dict(source=name,target=target,line=node.lineno,kind=kind))
            else:request(name,target,node.lineno,kind)
        def walk(node,lazy=False):
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda)):
                for child in ast.iter_child_nodes(node):
                    body=getattr(node,'body',None)
                    is_body=child in body if isinstance(body,list) else child is body
                    walk(child,lazy or is_body)
                return
            if isinstance(node,ast.Import):
                for a in node.names:record(a.name,node,lazy)
            elif isinstance(node,ast.ImportFrom):
                target=absolute(node.module,node.level);record(target,node,lazy)
                for a in node.names:
                    child=target+'.'+a.name
                    if a.name!='*' and resolve(child) is not None:record(child,node,lazy,'from_submodule')
            elif isinstance(node,ast.Call):
                fn=node.func;called=aliases.get(fn.id) if isinstance(fn,ast.Name) else None
                if isinstance(fn,ast.Attribute) and isinstance(fn.value,ast.Name) and aliases.get(fn.value.id)=='importlib' and fn.attr=='import_module':called='importlib.import_module'
                if called in ('__import__','importlib.import_module'):
                    arg=node.args[0] if node.args else next((k.value for k in node.keywords if k.arg=='name'),None)
                    if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and not arg.value.startswith('.'):
                        record(arg.value,node,lazy,'literal_dynamic_import')
                    elif lazy:dynamic_deferred.append(dict(source=name,line=node.lineno,call=ast.unparse(node)))
                    else:raise ValueError('Unresolved eager dynamic import '+name+':'+str(node.lineno))
            for child in ast.iter_child_nodes(node):walk(child,lazy)
        walk(tree)
    order=lambda e:(e['source'],e['line'],e['target'],e['kind'])
    return dict(version='repository_import_graph_v1',entries=list(entries),modules=dict(sorted(modules.items())),
        namespaces=dict(sorted(namespaces.items())),eager_edges=sorted(eager,key=order),deferred_edges=sorted(deferred,key=order),
        external_imports=sorted(external),deferred_dynamic_imports=dynamic_deferred,
        scope='Declared repository imports, conservative eager branches, deferred imports recorded; external packages not executed or recursively analyzed')

def check_guard(graph,guard):
    targets=sorted({e['target'] for e in graph['eager_edges']})
    for name in targets:guard.find_spec(name)
    return targets
