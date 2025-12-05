#!/bin/bash

cd $(dirname "${0}")
if [ $? -ne 0 ] ; then
  echo CHGDIR failed.
fi

# skip first three lines/results...
# pfs=$(jq -r '.urls[3:][][0]' package.json)

pfs=$(jq -r '.urls[][0]' package.json)

for pf in ${pfs} ; do
  if [[ "${mpyfile}" == *.json ]]; then
    continue
	fi

	if [[ "${pf}" == *.py ]]; then
	  pyfile="${pf}"
	  mpyfile="${pyfile%.py}.mpy"
	  # continue
	elif [[ "${pf}" == *.mpy ]]; then
	  mpyfile="${pf}"
	  pyfile="${mpyfile%.mpy}.py"
	  # continue
	fi

  echo ${pyfile}

	if [[ -f "${mpyfile}" && "${mpyfile}" -nt "${pyfile}" ]]; then
	  echo -e \\tskipping ${pyfile} since ${mpyfile} is NEWER\\n
	  continue
  fi

  echo COMPILING ${pyfile}
	mpy-cross "${pyfile}"
	echo
done
