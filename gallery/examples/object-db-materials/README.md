# Object library · material lab (proposal 5)

Material-first: materials with their density and measured reflectance spectra, and every object placed by what it
is made of on an Ashby chart (mass against bounding-box volume). 3D shows only in an object's peek.

- **App:** object database
- **Replaces:** `~/bam-waste-objects/views/Materials.base` and the spectra CSVs nobody can see without a script
- **Shows:** table grouped by family, chart (Vega-Lite dot plot, bars, 31 spectral lines, Ashby scatter with hull envelopes and a constant-density line), peek with a 3D orbit viewer
- **Data:** `../object-db-shelf/materials.json` (26 materials), `spectra.json` (31 spectra in 20 nm bins), `objects.json`; built by `../object-db-shelf/source/build.py`
- **Prior art:** USGS Spectral Library viewer (SpecLab), Ansys Granta / MatWeb material selectors, Ashby charts (Ashby, *Materials Selection in Mechanical Design*), TOMRA / Specim NIR sorting demos
