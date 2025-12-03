#!/bin/bash

cd $(dirname "${0}")
if [ $? -ne 0 ] ; then
  echo CHGDIR failed.
fi

mpys=$(jq -r '.urls[3:][][0]' package.json)

for mpyfile in ${mpys} ; do
  if [[ "${mpyfile}" == *.json ]]; then
    continue
	fi

	if [[ "${mpyfile}" == *.py ]]; then
	  continue
	fi

  pyfile="${mpyfile%.mpy}.py"

  echo ${pyfile}

	if [[ -f "${mpyfile}" && "${mpyfile}" -nt "${pyfile}" ]]; then
	  echo -e \\tskipping ${pyfile} since ${mpyfile} is NEWER\\n
	  continue
  fi

  echo COMPILING ${pyfile}
	mpy-cross "${pyfile}"
	echo
done
