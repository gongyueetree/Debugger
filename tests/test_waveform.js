import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeView, resizeView, formatSampleTime} from '../dist/wave-view.js';

test('time labels distinguish adjacent samples after zooming a high-rate capture', () => {
  assert.notEqual(formatSampleTime(0.004, 1 / 20e6), formatSampleTime(0.004 + 1 / 20e6, 1 / 20e6));
  assert.equal(formatSampleTime(0.004 + 1 / 20e6, 1 / 20e6), '4.00005 ms');
});

test('empty captures and shorter captures stay inside their data', () => {
  assert.deepEqual(normalizeView(0), {start: 0, size: 0});
  assert.deepEqual(normalizeView(12, {start: 100, size: 2}), {start: 0, size: 12});
  assert.deepEqual(normalizeView(1024, {start: 3072, size: 4096}), {start: 0, size: 1024});
});
test('zooming the full capture enables panning and preserves the pointer anchor', () => {
  const view = resizeView(4096, {start: 0, size: 4096}, 1024, 0.25);
  assert.deepEqual(view, {start: 768, size: 1024});
  assert.equal(view.start + view.size * 0.25, 4096 * 0.25);
  assert.equal(4096 - view.size, 3072);
});
test('pan and zoom clamp at both edges and at minimum zoom', () => {
  assert.deepEqual(normalizeView(4096, {start: -50, size: 256}), {start: 0, size: 256});
  assert.deepEqual(normalizeView(4096, {start: 10000, size: 256}), {start: 3840, size: 256});
  assert.deepEqual(resizeView(4096, {start: 3840, size: 256}, 1, 1), {start: 4064, size: 32});
  assert.deepEqual(resizeView(4096, {start: 3840, size: 256}, 10000), {start: 0, size: 4096});
});
