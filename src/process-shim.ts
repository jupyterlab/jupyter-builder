// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

/**
 * The `process` object provided to bundled modules that reference `process`.
 *
 * This is `process/browser` without `title`: xterm.js decides it is running
 * in Node.js when `'title' in process` and then never reads
 * `navigator.platform`, which leaves `isMac`, `isWindows` and `isLinux` all
 * false and turns off its platform specific keyboard handling.
 */
const shim = { ...require('process/browser') };
delete shim.title;

module.exports = shim;
