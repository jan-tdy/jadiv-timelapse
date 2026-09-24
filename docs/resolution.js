// Shared, testable logic for computing the target video resolution (web version).
// Loaded as a plain <script> in index.html (defines computeTargetResolution in the
// global scope) and can also be required() in Node.js tests.
(function (global, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        var lib = factory();
        global.computeTargetResolution = lib.computeTargetResolution;
        global.computeLetterboxLayout = lib.computeLetterboxLayout;
    }
}(typeof self !== 'undefined' ? self : this, function () {
    function computeTargetResolution(width, height, resolutionLabel, resolutionValue) {
        const isPortrait = height > width;
        let targetWidth, targetHeight;

        if (resolutionLabel.includes('4K') || resolutionLabel.includes('Full HD')) {
            // "4K"/"Full HD" denote the longer (horizontal) side of the video. For a
            // portrait photo, they're therefore applied to the height instead of the
            // width - otherwise you'd get an absurdly tall video instead of a sensible
            // vertical format.
            if (isPortrait) {
                targetHeight = resolutionValue;
                targetWidth = Math.round((resolutionValue / height) * width);
            } else {
                targetWidth = resolutionValue;
                targetHeight = Math.round((resolutionValue / width) * height);
            }
        } else {
            // "720p"/"480p"/"240p" denote the number of rows (height) and this applies
            // regardless of photo orientation.
            targetHeight = resolutionValue;
            targetWidth = Math.round((resolutionValue / height) * width);
        }

        // Ensure even numbers (required by video codecs)
        targetWidth -= targetWidth % 2;
        targetHeight -= targetHeight % 2;

        return { width: targetWidth, height: targetHeight };
    }

    // Computes the size and offset needed to place a photo (srcWidth x srcHeight) onto a
    // canvas with the target resolution (targetWidth x targetHeight) while preserving its
    // original aspect ratio ("letterbox"/"pillarbox"). The target resolution is derived
    // from the first photo in the selection, so other photos with a different aspect ratio
    // (a mix of portrait/landscape shots) would be stretched/distorted if drawn directly at
    // those dimensions - instead they're scaled down so they fit entirely within the
    // canvas, and the remaining space (black bars) is split evenly on both sides to keep
    // the photo centered.
    function computeLetterboxLayout(srcWidth, srcHeight, targetWidth, targetHeight) {
        const scale = Math.min(targetWidth / srcWidth, targetHeight / srcHeight);
        const newWidth = Math.min(Math.max(Math.round(srcWidth * scale), 1), targetWidth);
        const newHeight = Math.min(Math.max(Math.round(srcHeight * scale), 1), targetHeight);
        const xOffset = Math.floor((targetWidth - newWidth) / 2);
        const yOffset = Math.floor((targetHeight - newHeight) / 2);

        return { width: newWidth, height: newHeight, xOffset, yOffset };
    }

    return { computeTargetResolution, computeLetterboxLayout };
}));
