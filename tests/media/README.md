# Real-media test profiles

The configured tier always reports its selected profile in pytest's terminal summary. With no `HAWEDIT_MEDIA_ROOT`, it explicitly reports that real-media tests were not collected; zero skipped tests alone is not a quality claim.

Current sources (three original 4K Zar masters and the original five-minute excerpt):

```powershell
$env:HAWEDIT_MEDIA_ROOT = 'D:\HawEdit-media'
$env:HAWEDIT_MEDIA_PROFILE = 'current-zar'
.\.venv\Scripts\python.exe -m pytest tests/media
```

`current-provenance.json` preserves the hashes recorded by the source README. Every selected file is size- and SHA-256-verified, then container clocks/stream identities and actual video/audio decoding are checked. These checks establish source admission, not ASR accuracy, face coverage, caption quality or editorial acceptance. Missing or changed configured media fails.

The historical `legacy-ep29` profile continues to require the exact root-level `ep29-chunk50min.mp4`, SHA-256 `47235f4251961518d9bbae1ecbda9c7f5166c5baa57a2be98f5ec0eb64e6f863`, and runs all its original assertions. Explicitly select it with `HAWEDIT_MEDIA_PROFILE=legacy-ep29`. The default `auto` chooses legacy only when that named file exists, otherwise current; it never renames/re-hashes another source to satisfy the historical identity.

To clear the external-media tier for a normal clean gate:

```powershell
Remove-Item Env:HAWEDIT_MEDIA_ROOT -ErrorAction SilentlyContinue
Remove-Item Env:HAWEDIT_MEDIA_PROFILE -ErrorAction SilentlyContinue
```

Do not modify the original masters. New media/manifest changes require their own recorded provenance and checks.
