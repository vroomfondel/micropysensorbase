# echo \$0: $0

GIST_ID="c17ace0474819e400a8369e269c21dc6"
GIST_TOKEN="GENERATEMEATOKEN"
REPO_TOKEN="GENERATEMEATOKEN"
GITHUB_REPOSITORY="vroomfondel/micropysensorbase"

declare -a include_local_sh
include_local_sh[0]="$(dirname "$0")/include.local.sh"
include_local_sh[1]="$(dirname "$0")/scripts/include.local.sh"
include_local_sh[2]="$(dirname "$0")/../scripts/include.local.sh"
found=false

for path in "${include_local_sh[@]}"; do
  if [ -e "${path}" ]; then
    echo "${path} will be read..."
    source "${path}"
    found=true
    break
  fi
done

if [ "$found" = false ]; then
  echo "No include.local.sh file[s] found."
fi