// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import * as acorn from 'acorn';
import * as fs from 'fs-extra';
import * as path from 'path';

/**
 * What is recorded about one plugin.
 *
 * #### Notes
 * An object rather than the id on its own, so that a field can be added later
 * without JupyterLab having to read two shapes. `description` and `autoStart`
 * are the ones which could follow, as both are written as literals next to the
 * id. The token fields cannot, as they are values imported from other packages.
 */
export interface IRecordedPlugin {
  /**
   * The plugin id.
   */
  id: string;
}

/**
 * The key a default export is indexed under, which no identifier can collide
 * with.
 */
const DEFAULT = Symbol('default');

/**
 * A name bound at the top level of a module, or the default export.
 */
type BindingName = string | symbol;

/**
 * One of the extension's own files, indexed for lookups.
 */
interface IModule {
  /**
   * The parsed file.
   */
  program: acorn.Program;
  /**
   * What each top level name is bound to, including the default export and the
   * properties a CommonJS file assigns onto `exports`.
   */
  bindings: Map<BindingName, acorn.AnyNode>;
  /**
   * The file each `import * as name from './x'` refers to, by local name.
   */
  namespaces: Map<string, string>;
  /**
   * What each imported name refers to, by local name.
   */
  imports: Map<string, { file: string; name: BindingName }>;
  /**
   * The members assigned onto each TypeScript namespace in the file.
   */
  namespaceMembers: Map<string, Map<string, acorn.AnyNode>>;
}

/**
 * Where a binding was found, and what it is bound to.
 */
interface IResolved {
  file: string;
  node: acorn.AnyNode;
}

/**
 * Read the plugins a built extension module provides.
 *
 * @param modules - The modules to read, by the name they are exposed under.
 * @returns The plugins, by the name the module is exposed under.
 *
 * #### Notes
 * The extension is read rather than run: its files are parsed, the expression it
 * exports by default is resolved, and each plugin id is folded from the literals
 * and constants around it. Nothing the extension writes is executed, so reading
 * it cannot touch the machine it is built on, and a plugin added in a branch is
 * found whichever way that branch would have gone.
 *
 * A module is left out of the result when anything cannot be resolved, so that
 * JupyterLab loads it to discover its plugins as it would without this metadata.
 * Recording a list which is missing a plugin would be worse than recording
 * nothing: JupyterLab would take it for the whole set and could skip loading the
 * module while one of its plugins is enabled.
 */
export async function collectPlugins(
  modules: Record<string, string>
): Promise<Record<string, IRecordedPlugin[]>> {
  const collected: Record<string, IRecordedPlugin[]> = {};
  for (const [name, file] of Object.entries(modules)) {
    let ids: string[] | null;
    try {
      ids = readPluginIds(file);
    } catch (error) {
      console.warn(`Could not read the plugins ${name} provides: ${error}`);
      ids = null;
    }
    if (ids) {
      collected[name] = ids.map(id => ({ id }));
    } else {
      console.warn(
        `The plugins ${name} provides could not be read, so JupyterLab will ` +
          `load the module to discover them.`
      );
    }
  }
  return collected;
}

/**
 * Read the ids of the plugins one module provides.
 *
 * @returns The ids, or `null` when they cannot all be read.
 */
function readPluginIds(entryFile: string): string[] | null {
  const graph = new Map<string, IModule>();
  const entry = loadModule(graph, entryFile);
  const exported = entry.bindings.get(DEFAULT);
  if (!exported) {
    return null;
  }

  const plugins = pluginExpressions(graph, { file: entryFile, node: exported });
  if (!plugins) {
    return null;
  }

  const ids: string[] = [];
  for (const plugin of plugins) {
    const resolved = follow(graph, plugin);
    if (resolved.node.type !== 'ObjectExpression') {
      return null;
    }
    const property = resolved.node.properties.find(
      each =>
        each.type === 'Property' &&
        !each.computed &&
        propertyName(each) === 'id'
    );
    if (!property || property.type !== 'Property') {
      return null;
    }
    const id = foldString(graph, resolved.file, property.value);
    if (id === null) {
      return null;
    }
    ids.push(id);
  }
  return [...new Set(ids)];
}

/**
 * Every expression which can end up in the default export, whichever branch of
 * the module runs.
 *
 * @returns The expressions, or `null` when the shape of the export is not one
 * this understands.
 */
function pluginExpressions(
  graph: Map<string, IModule>,
  exported: IResolved
): IResolved[] | null {
  const { file, node } = follow(graph, exported);
  const module = graph.get(file);
  if (!module) {
    return null;
  }

  if (node.type === 'ObjectExpression') {
    return [{ file, node }];
  }
  if (node.type !== 'ArrayExpression') {
    return null;
  }

  const plugins: IResolved[] = [];
  for (const element of node.elements) {
    if (!element || element.type === 'SpreadElement') {
      return null;
    }
    plugins.push({ file, node: element });
  }

  // An array held in a name can be added to anywhere in the file, and reading
  // rather than running the module means both sides of a condition are found.
  const name = arrayName(graph, exported);
  if (name === null) {
    return plugins;
  }
  let understood = true;
  walk(module.program, each => {
    if (each.type !== 'CallExpression') {
      return;
    }
    const callee = each.callee;
    if (
      callee.type !== 'MemberExpression' ||
      callee.computed ||
      callee.object.type !== 'Identifier' ||
      callee.object.name !== name ||
      callee.property.type !== 'Identifier' ||
      (callee.property.name !== 'push' && callee.property.name !== 'unshift')
    ) {
      return;
    }
    for (const argument of each.arguments) {
      if (argument.type === 'SpreadElement') {
        understood = false;
      } else {
        plugins.push({ file, node: argument });
      }
    }
  });
  return understood ? plugins : null;
}

/**
 * The name the default export is held in, when it is held in one.
 */
function arrayName(
  graph: Map<string, IModule>,
  exported: IResolved
): string | null {
  let current = exported;
  const seen = new Set<string>();
  while (current.node.type === 'Identifier') {
    const key = `${current.file}#${current.node.name}`;
    if (seen.has(key)) {
      return null;
    }
    seen.add(key);
    const next = resolve(graph, current.file, current.node.name);
    if (!next) {
      return null;
    }
    if (next.node.type === 'ArrayExpression' && next.file === current.file) {
      return current.node.name;
    }
    current = next;
  }
  return null;
}

/**
 * Follow a chain of names to what it is finally bound to.
 */
function follow(graph: Map<string, IModule>, start: IResolved): IResolved {
  let current = start;
  const seen = new Set<string>();
  while (current.node.type === 'Identifier') {
    const key = `${current.file}#${current.node.name}`;
    if (seen.has(key)) {
      return current;
    }
    seen.add(key);
    const next = resolve(graph, current.file, current.node.name);
    if (!next) {
      return current;
    }
    current = next;
  }
  return current;
}

/**
 * Look one name up, in the file it is written in or the file it comes from.
 */
function resolve(
  graph: Map<string, IModule>,
  file: string,
  name: BindingName
): IResolved | null {
  const module = graph.get(file);
  if (!module) {
    return null;
  }
  const bound = module.bindings.get(name);
  if (bound) {
    return { file, node: bound };
  }
  if (typeof name !== 'string') {
    return null;
  }
  const imported = module.imports.get(name);
  if (!imported) {
    return null;
  }
  const node = graph.get(imported.file)?.bindings.get(imported.name);
  return node ? { file: imported.file, node } : null;
}

/**
 * Fold an expression to the string it is worth, or `null` when it depends on
 * something which is not written in the extension's own files.
 */
function foldString(
  graph: Map<string, IModule>,
  file: string,
  node: acorn.AnyNode,
  seen = new Set<string>()
): string | null {
  if (node.type === 'Literal') {
    return typeof node.value === 'string' ? node.value : null;
  }
  if (node.type === 'TemplateLiteral') {
    let text = '';
    for (let index = 0; index < node.quasis.length; index++) {
      text += node.quasis[index].value.cooked ?? '';
      const expression = node.expressions[index];
      if (expression) {
        const value = foldString(graph, file, expression, seen);
        if (value === null) {
          return null;
        }
        text += value;
      }
    }
    return text;
  }
  if (
    node.type === 'BinaryExpression' &&
    node.operator === '+' &&
    node.left.type !== 'PrivateIdentifier'
  ) {
    const left = foldString(graph, file, node.left, seen);
    const right = foldString(graph, file, node.right, seen);
    return left === null || right === null ? null : left + right;
  }
  if (node.type === 'Identifier') {
    const key = `${file}#${node.name}`;
    if (seen.has(key)) {
      return null;
    }
    seen.add(key);
    const bound = resolve(graph, file, node.name);
    return bound ? foldString(graph, bound.file, bound.node, seen) : null;
  }
  if (
    node.type === 'MemberExpression' &&
    !node.computed &&
    node.object.type === 'Identifier' &&
    node.property.type === 'Identifier'
  ) {
    return foldMember(graph, file, node.object.name, node.property.name, seen);
  }
  return null;
}

/**
 * Fold `object.property` where the object is a namespace or an object literal
 * written in the extension's own files.
 */
function foldMember(
  graph: Map<string, IModule>,
  file: string,
  object: string,
  property: string,
  seen: Set<string>
): string | null {
  const module = graph.get(file);
  if (!module) {
    return null;
  }

  // `import * as name from './x'`
  const namespace = module.namespaces.get(object);
  if (namespace) {
    const bound = resolve(graph, namespace, property);
    if (bound) {
      return foldString(graph, bound.file, bound.node, seen);
    }
    const value = graph
      .get(namespace)
      ?.namespaceMembers.get(object)
      ?.get(property);
    if (value) {
      return foldString(graph, namespace, value, seen);
    }
  }

  // a TypeScript `namespace`, in this file or the file it comes from
  const local = module.namespaceMembers.get(object)?.get(property);
  if (local) {
    return foldString(graph, file, local, seen);
  }
  const imported = module.imports.get(object);
  if (imported) {
    const value = graph
      .get(imported.file)
      ?.namespaceMembers.get(object)
      ?.get(property);
    if (value) {
      return foldString(graph, imported.file, value, seen);
    }
  }

  // an object literal held in a name, such as `const C = { NAME: '...' }`
  const held = resolve(graph, file, object);
  if (held && held.node.type === 'ObjectExpression') {
    for (const each of held.node.properties) {
      if (
        each.type === 'Property' &&
        !each.computed &&
        propertyName(each) === property
      ) {
        return foldString(graph, held.file, each.value, seen);
      }
    }
  }
  return null;
}

/**
 * Parse one file and the extension's own files it imports.
 */
function loadModule(graph: Map<string, IModule>, file: string): IModule {
  const existing = graph.get(file);
  if (existing) {
    return existing;
  }

  const program = acorn.parse(fs.readFileSync(file, 'utf8'), {
    ecmaVersion: 'latest',
    // A built extension is a module. A CommonJS build parses the same way and
    // only differs in how it names what it exports.
    sourceType: 'module',
    allowReturnOutsideFunction: true
  });

  const module: IModule = {
    program,
    bindings: new Map(),
    namespaces: new Map(),
    imports: new Map(),
    namespaceMembers: new Map()
  };
  graph.set(file, module);

  indexTopLevel(module, file);
  indexNamespaces(module);
  indexCommonJS(module);

  for (const node of program.body) {
    const source =
      (node.type === 'ImportDeclaration' ||
        node.type === 'ExportNamedDeclaration' ||
        node.type === 'ExportAllDeclaration') &&
      node.source
        ? node.source.value
        : null;
    if (typeof source === 'string') {
      const target = resolveFile(file, source);
      if (target) {
        loadModule(graph, target);
      }
    }
  }
  return module;
}

/**
 * Index what each top level statement binds.
 */
function indexTopLevel(module: IModule, file: string): void {
  for (const node of module.program.body) {
    if (node.type === 'ImportDeclaration') {
      const target =
        typeof node.source.value === 'string'
          ? resolveFile(file, node.source.value)
          : null;
      if (!target) {
        continue;
      }
      for (const specifier of node.specifiers) {
        if (specifier.type === 'ImportNamespaceSpecifier') {
          module.namespaces.set(specifier.local.name, target);
        } else if (specifier.type === 'ImportDefaultSpecifier') {
          module.imports.set(specifier.local.name, {
            file: target,
            name: DEFAULT
          });
        } else if (specifier.imported.type === 'Identifier') {
          module.imports.set(specifier.local.name, {
            file: target,
            name: specifier.imported.name
          });
        }
      }
    } else if (node.type === 'VariableDeclaration') {
      bindDeclarations(module, node);
    } else if (
      node.type === 'ExportNamedDeclaration' &&
      node.declaration?.type === 'VariableDeclaration'
    ) {
      bindDeclarations(module, node.declaration);
    } else if (node.type === 'ExportDefaultDeclaration') {
      module.bindings.set(DEFAULT, node.declaration);
    }
  }
}

/**
 * Bind each name a variable declaration introduces.
 */
function bindDeclarations(
  module: IModule,
  node: acorn.VariableDeclaration
): void {
  for (const declarator of node.declarations) {
    if (declarator.id.type === 'Identifier' && declarator.init) {
      module.bindings.set(declarator.id.name, declarator.init);
    }
  }
}

/**
 * Index the members of each TypeScript `namespace`.
 *
 * #### Notes
 * TypeScript writes `namespace Foo { export const X = 'y' }` as a function
 * taking `Foo` and assigning onto it, so the members are only visible as
 * assignments inside that function.
 */
function indexNamespaces(module: IModule): void {
  for (const node of module.program.body) {
    if (node.type !== 'ExpressionStatement') {
      continue;
    }
    const call = node.expression;
    if (call.type !== 'CallExpression') {
      continue;
    }
    const fn = call.callee;
    if (
      (fn.type !== 'FunctionExpression' &&
        fn.type !== 'ArrowFunctionExpression') ||
      fn.params.length !== 1 ||
      fn.params[0].type !== 'Identifier'
    ) {
      continue;
    }
    const name = fn.params[0].name;
    const members = module.namespaceMembers.get(name) ?? new Map();
    walk(fn.body as acorn.AnyNode, each => {
      if (each.type !== 'AssignmentExpression' || each.operator !== '=') {
        return;
      }
      const target = each.left;
      if (
        target.type !== 'MemberExpression' ||
        target.computed ||
        target.object.type !== 'Identifier' ||
        target.object.name !== name ||
        target.property.type !== 'Identifier'
      ) {
        return;
      }
      members.set(target.property.name, each.right);
    });
    if (members.size) {
      module.namespaceMembers.set(name, members);
    }
  }
}

/**
 * Index what a CommonJS build assigns onto `exports`.
 */
function indexCommonJS(module: IModule): void {
  walk(module.program, node => {
    if (node.type !== 'AssignmentExpression' || node.operator !== '=') {
      return;
    }
    const target = node.left;
    if (
      target.type !== 'MemberExpression' ||
      target.computed ||
      target.object.type !== 'Identifier' ||
      target.property.type !== 'Identifier'
    ) {
      return;
    }
    if (target.object.name === 'exports') {
      const name = target.property.name;
      module.bindings.set(name === 'default' ? DEFAULT : name, node.right);
    } else if (
      target.object.name === 'module' &&
      target.property.name === 'exports'
    ) {
      module.bindings.set(DEFAULT, node.right);
    }
  });
}

/**
 * The name of a property written without brackets.
 */
function propertyName(node: acorn.Property): string | null {
  if (node.key.type === 'Identifier') {
    return node.key.name;
  }
  if (node.key.type === 'Literal' && typeof node.key.value === 'string') {
    return node.key.value;
  }
  return null;
}

/**
 * Resolve one of the extension's own imports to a file.
 *
 * @returns The path, or `null` for anything which is not a JavaScript file of
 * this extension, such as a package or a stylesheet.
 */
function resolveFile(fromFile: string, request: string): string | null {
  if (!request.startsWith('.') && !path.isAbsolute(request)) {
    return null;
  }
  const base = path.resolve(path.dirname(fromFile), request);
  for (const candidate of [base, `${base}.js`, path.join(base, 'index.js')]) {
    if (
      candidate.endsWith('.js') &&
      fs.existsSync(candidate) &&
      fs.statSync(candidate).isFile()
    ) {
      return candidate;
    }
  }
  return null;
}

/**
 * Visit every node of a tree.
 */
function walk(node: acorn.AnyNode, visit: (node: acorn.AnyNode) => void): void {
  visit(node);
  for (const value of Object.values(
    node as unknown as Record<string, unknown>
  )) {
    if (Array.isArray(value)) {
      for (const child of value) {
        if (isNode(child)) {
          walk(child, visit);
        }
      }
    } else if (isNode(value)) {
      walk(value, visit);
    }
  }
}

/**
 * Whether a value is a node of the tree.
 */
function isNode(value: unknown): value is acorn.AnyNode {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as acorn.Node).type === 'string'
  );
}
