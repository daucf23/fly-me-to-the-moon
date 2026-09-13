# Sources and licenses

Original project code is available under the [MIT License](LICENSE).
Third-party materials retain their respective notices and terms below.

## Neural backend

`flybywire/neural/` is vendored from [nftechie/stonkfly](https://github.com/nftechie/stonkfly)
at commit `78ef3e05ab0fa086032098558d893667068944a0`, MIT License
([licenses/stonkfly-MIT.txt](licenses/stonkfly-MIT.txt)). Stonkfly's backend is in turn
adapted from the DOOMFLY project. Per-file upstream hashes and the single local
modification are recorded in [flybywire/upstream.json](flybywire/upstream.json).

## Wiring data

Connectivity and annotations come from the **MaleCNS v1.0** dataset
(HHMI Janelia FlyEM, Cambridge Connectomics Group, Google Research), released under
**CC BY 4.0**: <https://male-cns.janelia.org/download/>.
The dataset is downloaded to `data/` on first `flybywire prepare` and is not committed.

## Kerbal Space Program

KSP is a commercial game by Squad / Private Division. Nothing from it is redistributed here.
Remote control uses the [kRPC](https://github.com/krpc/krpc) mod (GPL-3.0) via its Python
client; the mod is installed into your own KSP `GameData/` and is not vendored.

## Video soundtrack

The v6 score is an original arrangement using **VSCO 2 Community Edition** acoustic
instrument recordings by Sam Gossner and Simon Dalzell / Versilian Studios, with
sample cutting by Elan Hickler / Soundemote. The recordings are released under
[CC0 1.0](licenses/VSCO2-CC0.txt). Source:
[sgossner/VSCO-2-CE](https://github.com/sgossner/VSCO-2-CE), pinned to commit
`440300901dfe9275fd84e0b7763af1f8443ae62e`.
Exact sample URLs and SHA-256 hashes are in
[scripts/media/v6-samples.json](scripts/media/v6-samples.json).
Samples and KSP footage are not committed. See [the edit notes](docs/video-edit-plan.md)
for the media workflow.
