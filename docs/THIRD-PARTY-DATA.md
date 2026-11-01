# Third-party data

`LICENSE` (MIT) covers data-ui's code and its own documentation. It does not cover what other people made. This page
lists what the repository redistributes, under which terms, and what stays out of a public copy.

| What | Where | Terms | What the terms ask |
|---|---|---|---|
| Google Scanned Objects (150 scanned meshes, re-encoded as GLB, and renders of them) | `gallery/examples/object-db-shelf/meshes/gso_*`, `thumbs/gso_*`; each row's `license` | CC BY 4.0 | Credit below; say the meshes were changed |
| EGAD evaluation set (30 meshes, re-encoded as GLB) | `gallery/examples/object-db-shelf/meshes/egad_*`; each row's `license` | BSD-3-Clause | Keep the notice below |
| Universal Robots UR5e model, through MuJoCo Menagerie | `gallery/examples/pid-tuning/media/ur5e_links.glb` and the link tables built from it (`robotics-arm`, `dashboard-cards`, `tests/browser/fixtures/p1b/arm/`) | BSD-3-Clause | Keep the notice below |
| USGS Spectral Library v7 (`usgs-splib07a`) | `gallery/examples/object-db-shelf/spectra.json` | US public domain | Credit is customary |
| Plastic and material spectra: HZDR RODARE 2448, de Vries & Garaba 2023, Ohall et al. 2025 | `gallery/examples/object-db-shelf/spectra.json`, averaged into 20 nm bins | CC BY 4.0 | Credit below; say they were binned |
| Natural Earth 1:110m countries | `packages/views/map/assets/countries-110m.json` | Public domain | Nothing |
| The map cases' data: OpenStreetMap rows and a Protomaps basemap, ESA WorldCover inside it, Natural Earth, Statistics Canada, CESI, BC, single Metro Vancouver and City of Vancouver figures; Noto Sans glyphs | `gallery/examples/map-*`, `packages/views/map/assets/glyphs/` | ODbL, CC BY 4.0, public domain, Statistics Canada Open Licence, OGL – Canada, OGL – British Columbia, facts with no open licence, OFL 1.1, file by file | `docs/MAP-DATA.md`: each credit and where it is; OpenStreetMap's is on the map itself |
| Every npm package in a build | `dist/LICENSES.md`, generated from the bundles | Each package's own | Shipped beside the kit |
| Part names, specs, prices and seller countries | `gallery/examples/robotparts-*`, `bench/scenarios/robotparts-*` | Facts from public listings and datasheets; each value cites its source | Names and marks stay their owners' |
| Vendor product photos and logos | `gallery/examples/robotparts-photos/media/`, `robotparts-actuators/photos/`, `robotparts-compare/photos/`, `filters-gallery/logos/`, `design-babble/stills/`, `bench/scenarios/robotparts-photos/media/`, `bench/scenarios/robotparts-actuators/photos/`, `bench/scenarios/actuator-charts/photos/` | Their owners'; hosted by robotparts linked to the source, removed on request | **Not licensed to anyone by this repository.** A public copy holds a one-pixel placeholder under each name (`tools/public-export.mjs`) |
| BAM, RobotParts, ObjectDB and Jidoka marks | `gallery/examples/brand-lineage/`, `gallery/examples/logo-rounds/` | Their owner's | MIT grants no trademark rights |

## Credits and notices

**Google Scanned Objects.** Downs, Francis, Koenig, Kinman, Hickman, Reymann, McHugh, Vanhoucke, "Google Scanned Objects:
A High-Quality Dataset of 3D Scanned Household Items", ICRA 2022. CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Changed: decimated and re-encoded as GLB, rendered to thumbnails.

**Spectra (CC BY 4.0, averaged into 20 nm bins).** de Lima Ribeiro, Fuchs, Lorenz, Roeder, Heitmann, Gloaguen 2023,
doi:10.14278/rodare.2448. de Vries & Garaba 2023, doi:10.4121/769cc482-b104-4927-a94b-b16f6618c3b3.v1. Ohall, Bisson &
Rivero-Calle 2025, doi:10.4121/059551d3-2383-4e20-af2d-011c9a59d3ac.v1.

**EGAD.** Morrison, Corke, Leitner, "EGAD! An Evolved Grasping Analysis Dataset for Diversity and Reproducibility in
Robotic Manipulation", RA-L 2020. (c) Doug Morrison, Australian Centre for Robotic Vision, Queensland University of
Technology, 2020.

**UR5e model.** Copyright 2018 ROS Industrial Consortium. https://github.com/google-deepmind/mujoco_menagerie

The BSD-3-Clause terms of both, as their copyright holders published them:

> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
> following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
> disclaimer.
>
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
> disclaimer in the documentation and/or other materials provided with the distribution.
>
> 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
> products derived from this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
> INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
> DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
> SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
> SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
> WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
> OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
