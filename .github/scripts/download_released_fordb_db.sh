#!/usr/bin/env bash
# Fetch the released DB and its matching allocator state for a ForDB dry-run.
# Reuse the producer's naming and split-assembly contracts from seforim-tool.
set -euo pipefail

tag=${1:?usage: download_released_fordb_db.sh <release-tag> <output-dir> <seforim-tool>}
dest=${2:?missing output directory}
tool=${3:?missing SeforimLibrary checkout}
repo=Otzaria/SeforimLibrary
mkdir -p "$dest"
for output in seforim.db seforim.db.buildstate build_provenance.json; do
  [ ! -e "$dest/$output" ] || { echo "output already exists: $dest/$output" >&2; exit 1; }
done
work=$(mktemp -d "$dest/.released-db.XXXXXX")
trap 'rm -rf "$work"' EXIT
# shellcheck source=/dev/null
. "$tool/.github/scripts/db_asset_names.sh"
gh release view "$tag" -R "$repo" --json assets > "$work/release.json"

# download_full_db_by_name deliberately does not authenticate single-file
# downloads. Pin small metadata and single archives to the release API digest.
download_verified() {
  local asset=$1 digest actual
  digest=$(jq -er --arg name "$asset" '
    [.assets[] | select(.name == $name)] |
    if length == 1 then .[0].digest else error("missing or duplicate release asset") end
  ' "$work/release.json")
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo "missing sha256 digest for $asset" >&2; return 1;
  }
  gh release download "$tag" -R "$repo" -p "$asset" -D "$work"
  actual=$(sha256sum "$work/$asset" | cut -d' ' -f1)
  [ "$actual" = "${digest#sha256:}" ] || {
    echo "checksum mismatch: $asset" >&2; return 1;
  }
}

db_asset=$(jq -er "$FULL_DB_ASSET_JQ | .name // empty" "$work/release.json")
manifest=$(jq -r "$FULL_DB_ASSET_JQ | .manifest // empty" "$work/release.json")
download_verified build_provenance.json
# New provenance identifies the schema explicitly; older provenance can still
# use the producer's highest-schema asset selector above.
if jq -e '.db_schema != null' "$work/build_provenance.json" >/dev/null; then
  schema=$(jq -er '.db_schema.db_schema_version | select(type == "number" and . > 0 and . == floor)' \
    "$work/build_provenance.json")
  [ "$db_asset" = "$(full_db_asset_name "$schema")" ] || {
    echo "DB asset disagrees with build provenance: $db_asset" >&2; exit 1;
  }
fi

if [ -n "$manifest" ]; then
  download_verified "$manifest"
  # Validate before using any part name as a gh pattern or a local path. The
  # shared assembler then checks every part and the complete archive digest.
  jq -e --arg archive "$db_asset" '
    .schemaVersion == 1 and .archive == $archive and
    (.sha256 | test("^[0-9a-f]{64}$")) and
    (.parts | type == "array" and length > 0) and
    ([.parts[].name] | length == (unique | length)) and
    all(.parts[];
      (.name | startswith($archive + ".part-")) and
      (.name | ltrimstr($archive + ".part-") | test("^[0-9]{3,}$")) and
      (.sha256 | test("^[0-9a-f]{64}$")))
  ' "$work/$manifest" >/dev/null
  while IFS= read -r part; do
    gh release download "$tag" -R "$repo" -p "$part" -D "$work"
  done < <(jq -r '.parts[].name' "$work/$manifest")
  bash "$tool/.github/scripts/assemble_split_asset.sh" "$work/$manifest" "$work/$db_asset"
  rm -f "$work/$db_asset.part-"*
else
  download_verified "$db_asset"
fi
unzstd --long=31 --memory=2048MB -f "$work/$db_asset" -o "$work/seforim.db"
rm -f "$work/$db_asset"
# The state must sit at <db>.buildstate, independent of the published DB name.
download_verified seforim.db.buildstate.zst
unzstd -f "$work/seforim.db.buildstate.zst" -o "$work/seforim.db.buildstate"
mv "$work/seforim.db" "$work/seforim.db.buildstate" "$work/build_provenance.json" "$dest/"
