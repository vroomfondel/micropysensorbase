#!/bin/bash

cd $(dirname "${0}")
if [ $? -ne 0 ] ; then
  echo CHGDIR failed.
fi

pys=$(jq -r '.urls[3:][][0]' package.json)

for pyfile in ${pys} ; do
  if [[ "${pyfile}" == *.json ]]; then
    continue
	fi

  mpyfile="${pyfile%.py}.mpy"

  echo ${pyfile}

	if [[ -f "${mpyfile}" && "${mpyfile}" -nt "${pyfile}" ]]; then
	  echo -e \\tskipping ${pyfile} since ${mpyfile} is NEWER\\n
	  continue
  fi

  echo COMPILING ${pyfile}
	mpy-cross "${pyfile}"
	echo
done
