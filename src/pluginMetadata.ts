// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import * as fs from 'fs-extra';
import * as os from 'os';
import * as path from 'path';
import { NormalModuleReplacementPlugin, rspack } from '@rspack/core';

/**
 * The module every import of the extension is replaced with.
 *
 * #### Notes
 * A plugin declares its id and description as literals in the extension's own
 * source, but it reaches for tokens, icons and widgets in other packages. Those
 * packages read browser globals when they are imported, which is why they are
 * replaced rather than bundled: reading the literals must not depend on the
 * extension being loadable outside a browser.
 */
const STUB_SOURCE = `
function makeStub() {
  const target = function () {
    return makeStub();
  };
  return new Proxy(target, {
    get(_target, property) {
      switch (property) {
        case '__esModule':
          return true;
        // A stub must not look like a promise, or awaiting it never settles.
        case 'then':
          return undefined;
        case Symbol.toPrimitive:
          return () => '';
        case Symbol.iterator:
          return function* () {};
        default:
          return makeStub();
      }
    },
    apply() {
      return makeStub();
    },
    construct() {
      return makeStub();
    }
  });
}
module.exports = makeStub();
`;

/**
 * File extensions the extension may import which are not JavaScript.
 */
const ASSET_PATTERN =
  /\.(css|less|sass|scss|svg|png|jpe?g|gif|webp|woff2?|eot|ttf|html|txt|md)$/;

/**
 * A built extension module, as the bundle exports it.
 */
interface IExtensionModule {
  __esModule?: boolean;
  default?: unknown;
}

/**
 * Read the plugins an extension module provides, the way JupyterLab does.
 *
 * #### Notes
 * Kept in step with `getPlugins` in JupyterLab's `dev_mode/index.js`, so that
 * the recorded ids are the ids of the plugins JupyterLab will find.
 */
function getPlugins(extension: IExtensionModule): unknown[] {
  let exports: unknown;
  if (Object.prototype.hasOwnProperty.call(extension, '__esModule')) {
    exports = extension.default;
  } else {
    exports = extension;
  }
  return Array.isArray(exports) ? exports : [exports];
}

/**
 * Read the id of one plugin, or `undefined` when it has none.
 */
function readPluginId(plugin: unknown): unknown {
  if (typeof plugin !== 'object' || plugin === null) {
    return undefined;
  }
  return (plugin as { id?: unknown }).id;
}

/**
 * What is recorded about one plugin.
 *
 * #### Notes
 * An object rather than the id on its own, so that a field can be added later
 * without JupyterLab having to read two shapes. `description` and `autoStart`
 * are the ones which could follow; the token fields cannot, as they are objects
 * imported from other packages which the stand-in replaces.
 */
export interface IRecordedPlugin {
  /**
   * The plugin id.
   */
  id: string;
}

/**
 * Read the plugins a built extension module provides.
 *
 * @param modules - The modules to read, by the name they are exposed under.
 * @returns The plugins, by the name the module is exposed under.
 *
 * #### Notes
 * A module is left out of the result when its plugins cannot be read, so that
 * JupyterLab keeps loading it as it would without this metadata. Reading is
 * best-effort by design: it evaluates the module with every import replaced by
 * a stand-in, and an extension is free to do something at import time which
 * that does not survive.
 */
export async function collectPlugins(
  modules: Record<string, string>
): Promise<Record<string, IRecordedPlugin[]>> {
  const names = Object.keys(modules);
  if (names.length === 0) {
    return {};
  }

  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), 'jupyter-builder-'));
  try {
    const stubPath = path.join(workDir, 'stub.js');
    fs.writeFileSync(stubPath, STUB_SOURCE);

    const entry: Record<string, string> = {};
    names.forEach((name, index) => {
      entry[`module${index}`] = modules[name];
    });

    await runCompilation(entry, workDir, stubPath);

    const collected: Record<string, IRecordedPlugin[]> = {};
    names.forEach((name, index) => {
      const plugins = readPlugins(path.join(workDir, `module${index}.js`));
      if (plugins) {
        collected[name] = plugins;
      }
    });
    return collected;
  } catch (error) {
    console.warn(
      `Could not read the plugins of this extension, so JupyterLab will ` +
        `load it to discover them: ${error}`
    );
    return {};
  } finally {
    fs.removeSync(workDir);
  }
}

/**
 * Whether a request is for something other than the extension's own source.
 */
function isForeign(request: string): boolean {
  const isRelative = request.startsWith('.') || path.isAbsolute(request);
  return !isRelative || ASSET_PATTERN.test(request);
}

/**
 * Bundle the modules for Node, with every import replaced by the stub.
 */
function runCompilation(
  entry: Record<string, string>,
  workDir: string,
  stubPath: string
): Promise<void> {
  const compiler = rspack({
    mode: 'development',
    devtool: false,
    target: 'node',
    entry,
    output: {
      path: workDir,
      filename: '[name].js',
      library: { type: 'commonjs2' }
    },
    plugins: [
      new NormalModuleReplacementPlugin(/.*/, resource => {
        if (isForeign(resource.request)) {
          resource.request = stubPath;
        }
      })
    ],
    infrastructureLogging: { level: 'error' },
    stats: 'errors-only'
  });

  return new Promise<void>((resolve, reject) => {
    compiler.run((error, stats) => {
      compiler.close(() => {
        if (error) {
          return reject(error);
        }
        if (stats?.hasErrors()) {
          const { errors } = stats.toJson({ errors: true, all: false });
          return reject(
            new Error(errors?.map(each => each.message).join('\n') ?? 'unknown')
          );
        }
        resolve();
      });
    });
  });
}

/**
 * Evaluate one bundled module and read the plugins it provides.
 *
 * @returns The plugins, or `null` when they cannot all be read.
 */
function readPlugins(bundlePath: string): IRecordedPlugin[] | null {
  let plugins: unknown[];
  try {
    plugins = getPlugins(require(bundlePath) as IExtensionModule);
  } catch (error) {
    console.warn(`Could not evaluate ${bundlePath} to read plugins:`, error);
    return null;
  }
  const ids = plugins.map(readPluginId);
  if (ids.some(id => typeof id !== 'string')) {
    // A partial list is worse than none: JupyterLab would take it for the whole
    // set of plugins the module provides and could skip loading the module
    // while one of its plugins is enabled.
    return null;
  }
  return (ids as string[]).map(id => ({ id }));
}
