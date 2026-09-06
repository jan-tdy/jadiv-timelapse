// Ľahký test bez frameworku pre docs/resolution.js - spúšťa sa cez `node docs/test/resolution.test.js`.
'use strict';

const assert = require('assert');
const path = require('path');
const computeTargetResolution = require(path.join(__dirname, '..', 'resolution.js'));

let passed = 0;

function test(name, fn) {
    try {
        fn();
        passed++;
        console.log(`  ok - ${name}`);
    } catch (err) {
        console.error(`  FAIL - ${name}`);
        console.error(err);
        process.exitCode = 1;
    }
}

function assertResolution(width, height, label, value, expected, message) {
    const result = computeTargetResolution(width, height, label, value);
    assert.deepStrictEqual(result, expected, message);
}

console.log('computeTargetResolution:');

test('Full HD landscape uses the long side as width', () => {
    assertResolution(3840, 2160, 'Full HD (Plynulé prehrávanie)', 1920, { width: 1920, height: 1080 });
});

test('Full HD portrait uses the long side as height', () => {
    assertResolution(2160, 3840, 'Full HD (Plynulé prehrávanie)', 1920, { width: 1080, height: 1920 });
});

test('4K landscape uses the long side as width', () => {
    assertResolution(1920, 1080, '4K (Vysoká kvalita)', 3840, { width: 3840, height: 2160 });
});

test('4K portrait uses the long side as height', () => {
    assertResolution(1080, 1920, '4K (Vysoká kvalita)', 3840, { width: 2160, height: 3840 });
});

test('720p always targets height regardless of orientation (landscape)', () => {
    assertResolution(1920, 1080, 'HD (720p)', 720, { width: 1280, height: 720 });
});

test('720p always targets height regardless of orientation (portrait)', () => {
    assertResolution(1080, 1920, 'HD (720p)', 720, { width: 404, height: 720 });
});

test('480p rounds an odd aspect ratio down to an even width', () => {
    assertResolution(640, 427, 'SD (480p - malé)', 480, { width: 718, height: 480 });
});

test('240p works with plain landscape photos', () => {
    assertResolution(1000, 750, 'Nízka kvalita (240p - veľmi malé)', 240, { width: 320, height: 240 });
});

test('rounds to the nearest pixel (not truncating) before enforcing even numbers', () => {
    // 1799 / 1000 * 500 = 899.5 -> rounds to 900 (already even, no adjustment needed).
    assertResolution(500, 1000, 'HD (720p)', 1799, { width: 900, height: 1798 });
});

test('result is always even, across a range of odd input dimensions', () => {
    for (let width = 97; width < 105; width++) {
        for (let height = 97; height < 105; height++) {
            const { width: targetWidth, height: targetHeight } = computeTargetResolution(
                width, height, 'HD (720p)', 720
            );
            assert.strictEqual(targetWidth % 2, 0, `width ${targetWidth} should be even`);
            assert.strictEqual(targetHeight % 2, 0, `height ${targetHeight} should be even`);
        }
    }
});

if (process.exitCode) {
    console.error(`\n${passed} passed, some tests FAILED.`);
    process.exit(1);
} else {
    console.log(`\nAll ${passed} tests passed.`);
}
