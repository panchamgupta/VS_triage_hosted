(function (global) {
    function QueryMol(text) {
        this.text = String(text || "");
    }

    QueryMol.prototype.get_smarts = function () {
        return this.text;
    };

    QueryMol.prototype.delete = function () {};

    function Mol(text) {
        this.text = String(text || "");
    }

    Mol.prototype.get_smiles = function () {
        return this.text;
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
        return [];
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