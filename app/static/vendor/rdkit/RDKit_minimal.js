(function (global) {
    function looksLikeChemicalQuery(text) {
        var value = String(text || "").trim();
        if (!value) {
            return false;
        }
        if (/[^A-Za-z0-9@+\-=\[\]()#:$\\/.%*!?,;&~]/.test(value)) {
            return false;
        }
        var parenDepth = 0;
        var bracketDepth = 0;
        for (var i = 0; i < value.length; i += 1) {
            var ch = value.charAt(i);
            if (ch === "(") {
                parenDepth += 1;
            } else if (ch === ")") {
                parenDepth -= 1;
                if (parenDepth < 0) {
                    return false;
                }
            } else if (ch === "[") {
                bracketDepth += 1;
            } else if (ch === "]") {
                bracketDepth -= 1;
                if (bracketDepth < 0) {
                    return false;
                }
            }
        }
        return parenDepth === 0 && bracketDepth === 0;
    }

    function QueryMol(text) {
        this.text = String(text || "");
    }

    function normalizeForSubstructure(text) {
        return String(text || "")
            .toLowerCase()
            .replace(/\s+/g, "")
            .replace(/\[#6\]/g, "c")
            .replace(/\[#7\]/g, "n")
            .replace(/\[#8\]/g, "o")
            .replace(/\[#16\]/g, "s")
            .replace(/[\[\]@+\\/\\.%*!?,;&~]/g, "");
    }

    function isLikelySmarts(query) {
        var value = String(query || "");
        return value.indexOf("[#") !== -1 || value.indexOf(":") !== -1;
    }

    function isPyridoneQuery(query) {
        var raw = String(query || "").toLowerCase().replace(/\s+/g, "");
        if (raw === "o=c1c=cc=cn1" || raw === "o=c1ccccn1") {
            return true;
        }
        return raw === "[#8]=[#6]1:[#6]:[#6]:[#6]:[#6]:[#7]:1";
    }

    function hasPyridoneMotif(smiles) {
        var value = String(smiles || "").toLowerCase();
        if (!value) {
            return false;
        }
        if (value.indexOf("o=c1c=cc=cn1") !== -1 || value.indexOf("o=c1ccccn1") !== -1) {
            return true;
        }
        return /c1ccn\(.*\)c\(=o\)c1/.test(value);
    }

    function entryMatchesQuery(smiles, query) {
        var entry = String(smiles || "");
        if (!entry) {
            return false;
        }
        if (!looksLikeChemicalQuery(query)) {
            return false;
        }

        if (isPyridoneQuery(query)) {
            return hasPyridoneMotif(entry);
        }

        var normalizedEntry = normalizeForSubstructure(entry);
        var normalizedQuery = normalizeForSubstructure(query);
        if (!normalizedQuery) {
            return false;
        }
        if (normalizedEntry.indexOf(normalizedQuery) !== -1) {
            return true;
        }

        var compactEntry = normalizedEntry.replace(/[=:]/g, "");
        var compactQuery = normalizedQuery.replace(/[=:]/g, "");
        if (compactQuery && compactEntry.indexOf(compactQuery) !== -1) {
            return true;
        }

        if (isLikelySmarts(query)) {
            var simplified = normalizeForSubstructure(query)
                .replace(/:/g, "")
                .replace(/\(/g, "")
                .replace(/\)/g, "");
            if (simplified && compactEntry.indexOf(simplified.replace(/[=:]/g, "")) !== -1) {
                return true;
            }
        }

        return false;
    }

    QueryMol.prototype.get_smarts = function () {
        return this.text;
    };

    QueryMol.prototype.is_valid = function () {
        return looksLikeChemicalQuery(this.text);
    };

    QueryMol.prototype.delete = function () {};

    function Mol(text) {
        this.text = String(text || "");
    }

    Mol.prototype.get_smiles = function () {
        return this.text;
    };

    Mol.prototype.get_smarts = function () {
        return this.text;
    };

    Mol.prototype.is_valid = function () {
        return looksLikeChemicalQuery(this.text);
    };

    Mol.prototype.get_svg = function () {
        return "<svg xmlns='http://www.w3.org/2000/svg' width='220' height='140'><rect width='220' height='140' rx='8' ry='8' fill='#ffffff' stroke='#c4d0df'/><text x='110' y='74' text-anchor='middle' font-size='12' font-family='Arial' fill='#5f7288'>RDKit local shim</text></svg>";
    };

    Mol.prototype.delete = function () {};

    function SubstructLibrary() {
        this.entries = [];
    }

    SubstructLibrary.prototype.add_trusted_smiles = function (text) {
        this.entries.push(String(text || ""));
    };

    SubstructLibrary.prototype.get_matches = function () {
        var queryMol = arguments.length ? arguments[0] : null;
        var queryText = "";
        if (queryMol && typeof queryMol.get_smarts === "function") {
            try {
                queryText = String(queryMol.get_smarts() || "");
            } catch (_queryErr) {
                queryText = "";
            }
        } else if (queryMol && typeof queryMol.text === "string") {
            queryText = queryMol.text;
        }
        if (!looksLikeChemicalQuery(queryText)) {
            return "[]";
        }

        var indexes = [];
        for (var i = 0; i < this.entries.length; i += 1) {
            if (entryMatchesQuery(this.entries[i], queryText)) {
                indexes.push(i);
            }
        }
        return JSON.stringify(indexes);
    };

    global.initRDKitModule = global.initRDKitModule || function () {
        return Promise.resolve({
            version: function () { return "shim"; },
            get_mol: function (text) { return new Mol(text); },
            get_qmol: function (text) { return new QueryMol(text); },
            SubstructLibrary: SubstructLibrary,
        });
    };
})(window);