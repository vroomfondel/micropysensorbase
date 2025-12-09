# echo \$0: $0

GIST_ID="c17ace0474819e400a8369e269c21dc6"
GIST_TOKEN="GENERATEMEATOKEN"
REPO_TOKEN="GENERATEMEATOKEN"
GITHUB_REPOSITORY="vroomfondel/micropysensorbase"

include_local_sh="$(dirname "$0")/include.local.sh"
include_local_sh2="$(dirname "$0")/scripts/include.local.sh"

if [ -e "${include_local_sh}" ] ; then
  echo "${include_local_sh}" to be read...
  source "${include_local_sh}"
else
  # echo "${include_local_sh}" does not exist...
  if [ -e "${include_local_sh2}" ] ; then
    echo "${include_local_sh2}" to be read...
    source "${include_local_sh2}"
  else
    echo NEITHER "${include_local_sh}" NOR "${include_local_sh2}" exist...
  fi
fi