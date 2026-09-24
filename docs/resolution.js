// Zdieľaná, testovateľná logika výpočtu cieľového rozlíšenia videa (web verzia).
// Načítava sa ako obyčajný <script> v index.html (definuje computeTargetResolution
// v globálnom scope) a zároveň sa dá požadovať cez require() v Node.js testoch.
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

    // Vypočíta rozmery a odsadenie potrebné na vloženie fotky (srcWidth x srcHeight) do
    // plátna s cieľovým rozlíšením (targetWidth x targetHeight) so zachovaním jej pôvodného
    // pomeru strán ("letterbox"/"pillarbox"). Cieľové rozlíšenie sa určuje z prvej fotky vo
    // výbere, takže ďalšie fotky s iným pomerom strán (namixované portrét/landscape) by sa
    // pri priamom vykreslení na tieto rozmery natiahli/skreslili - namiesto toho sa zmenšia
    // tak, aby sa celé zmestili dovnútra, a zvyšný priestor (čierne pruhy) sa rozdelí
    // rovnomerne na obe strany, aby bola fotka vycentrovaná.
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
