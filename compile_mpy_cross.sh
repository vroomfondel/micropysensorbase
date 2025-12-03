#!/bin/bash

cd $(dirname "${0}")
if [ $? -ne 0 ] ; then
  echo CHGDIR failed.
fi

mpys=$(jq -r '.urls[3:][][0]' package.json)

for i in $mpys ; do
  if [[ "${i}" == *.json ]]; then
    continue
	fi

  pyfile="${i%.mpy}.py"

  echo ${pyfile}

	if [[ -f "${i}" && "${i}" -nt "${pyfile}" ]]; then
	  echo -e \\tskipping ${pyfile} since ${i} is NEWER\\n
	  continue
  fi

  echo COMPILING ${pyfile}
	mpy-cross "${pyfile}"
	echo
done
