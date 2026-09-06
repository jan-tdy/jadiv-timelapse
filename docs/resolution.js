// Zdieľaná, testovateľná logika výpočtu cieľového rozlíšenia videa (web verzia).
// Načítava sa ako obyčajný <script> v index.html (definuje computeTargetResolution
// v globálnom scope) a zároveň sa dá požadovať cez require() v Node.js testoch.
(function (global, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        global.computeTargetResolution = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    function computeTargetResolution(width, height, resolutionLabel, resolutionValue) {
        const isPortrait = height > width;
        let targetWidth, targetHeight;

        if (resolutionLabel.includes('4K') || resolutionLabel.includes('Full HD')) {
            // "4K"/"Full HD" udávajú dlhšiu (vodorovnú) stranu videa. Pri fotke na výšku
            // (portrét) sa preto aplikujú na výšku, nie na šírku — inak by vyšlo
            // absurdne vysoké video namiesto rozumného zvislého formátu.
            if (isPortrait) {
                targetHeight = resolutionValue;
                targetWidth = Math.round((resolutionValue / height) * width);
            } else {
                targetWidth = resolutionValue;
                targetHeight = Math.round((resolutionValue / width) * height);
            }
        } else {
            // "720p"/"480p"/"240p" udávajú počet riadkov (výšku) a platí to bez ohľadu
            // na orientáciu fotky.
            targetHeight = resolutionValue;
            targetWidth = Math.round((resolutionValue / height) * width);
        }

        // Zabezpečenie párnych čísel (vyžadujú to video kodeky)
        targetWidth -= targetWidth % 2;
        targetHeight -= targetHeight % 2;

        return { width: targetWidth, height: targetHeight };
    }

    return computeTargetResolution;
}));
