# Object library · family tree (proposal 3)

Taxonomy-first: the library as its own structure, family → material → type, every node with its library-wide
instance count. A graph (React Flow) and an outline (the table's tree); a type's peek, and the prototype page's
full-height stage, show its representative object in 3D.

- **App:** object database
- **Replaces:** `~/bam-waste-objects/views/Types.base` and `Materials.base` (flat tables with a backlink formula)
- **Shows:** graph (dagre layout, edges from `parent`), table with `tree: {parent}`, cards of types with `mesh:`, a 3D stage beside the graph (prototype page)
- **Data:** `../object-db-shelf/taxonomy.json` (families, 26 materials and 72 types from their frontmatter links; built by `../object-db-shelf/source/build.py`)
- **Prior art:** ImageNet / WordNet's synset explorer, Objaverse-LVIS category browser, Greyparrot's waste taxonomy, the GBIF / iNaturalist taxon tree
