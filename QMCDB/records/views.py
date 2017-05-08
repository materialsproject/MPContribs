from __future__ import division
from django.shortcuts import render
from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import login_required
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from records.forms import MaterialQueryForm, MaterialSubmissionForm
from records.models import QMCDBSet
from records.serializers import QMCDBSetSerializer
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser
from django.utils.six import BytesIO
from django.utils.safestring import mark_safe
import numpy as np

def manual_qmc_record_submission(request):
  if request.method == "POST":
    mat_form = MaterialSubmissionForm(request.POST)

    if mat_form.is_valid():
      mat_form.save()
      return HttpResponseRedirect('/thanks/')
  else:
    mat_form = MaterialSubmissionForm()

  return render(request, 'materialsubmissionform.html', {'form':mat_form})

@api_view(['GET', 'POST'])
def rest_submission(request):
	if request.method == "POST":
		serializer = QMCDBSetSerializer(data=request.data)
		if serializer.is_valid():
			serializer.save()
			return Response(serializer.data, status=status.HTTP_201_CREATED)
		return Response([serializer.errors], status=status.HTTP_400_BAD_REQUEST)
	return HttpResponse(status=400)

def material_overview(request,material_id):
  def dash_if_empty(inp):
    if inp == '' or inp == None:
      return mark_safe('&mdash;')
    else:
      return inp

  qmcdbset = QMCDBSet.objects(pk=material_id)[0]
  structure = qmcdbset.primitive_structure
  H2eV = 27.2114
  records = qmcdbset.records

  provenance = [{
    'nfu':r.structure.nfu,
    'jastrow':r.jastrow[0],
    'form':r.get_trial_wfn_form_display(),
    'kpt_values': r.get_kpoints_display(),
    'optimization': r.optimization[0],
    'dft_source': {
        'pseudopotential': r.trial_source.trial_source.get_pseudopotential_display(),
        'kmesh': 'x'.join([str(k) for k in r.trial_source.trial_source.kmesh]),
        'basis': mark_safe('</br>'.join(['&emsp;'+b.strip() if b[0]==' ' else b.strip() for b in r.trial_source.trial_source.basis_set.split('\n')]))
      }
    } for r in records]

  ## TABLE DATA ##
  attributes = {
    'formula': dash_if_empty(qmcdbset.formula),
    'publication': {
      'doi': dash_if_empty(qmcdbset.DOI),
      'title': dash_if_empty(qmcdbset.pub_title),
      'authors': dash_if_empty(qmcdbset.pub_authors),
      'date': dash_if_empty(qmcdbset.pub_date),
      'journal': dash_if_empty(qmcdbset.pub_journal)
      },
    'structure': {
      'spacegroup': dash_if_empty(structure.spacegroup),
      'lattice_a': dash_if_empty(structure.lattice_a),
      'lattice_b': dash_if_empty(structure.lattice_b),
      'lattice_c': dash_if_empty(structure.lattice_c),
      'lattice_alpha': dash_if_empty(structure.lattice_alpha),
      'lattice_beta': dash_if_empty(structure.lattice_beta),
      'lattice_gamma': dash_if_empty(structure.lattice_gamma)
      },
    'provenance': provenance,
    'cif': mark_safe(qmcdbset.primitive_structure.cif.replace("'","\\'").replace("\n","\\n"))
  }

  ## CHART ##

  total_energies = str([
    [1/r.structure.nfu,
    round(r.total_energy*H2eV/r.structure.nfu,5)] 
    for r in records])
  
  total_energy_errors = str([
    [1/r.structure.nfu,
    round((r.total_energy-r.total_energy_error/2)*H2eV/r.structure.nfu,5),
    round((r.total_energy+r.total_energy_error/2)*H2eV/r.structure.nfu,5)] 
    for r in records])

  fit = qmcdbset.linfit_energy
  max_pt = max([1/r.structure.nfu for r in records])
  linear_fit = str([
    [0, round(fit['c0'][0]*H2eV,5)],
    [max_pt, round((max_pt*fit['c1'][0]+fit['c0'][0])*H2eV,5)]
    ])
  nfu = str([1/r.structure.nfu for r in records][::-1])

  cht = {
    'total_energies':total_energies,
    'total_energy_errors':total_energy_errors,
    'linear_fit':linear_fit,
    'nfu':nfu
    }

  ## PROPERTIES ##
  y_int = {'value':round(fit['c0'][0]*H2eV,5), 'error':round(fit['c0'][1]*H2eV,5)}
  formation_enthalpy = qmcdbset.formation_enthalpy
  if formation_enthalpy != None:
    formation_enthalpy = {'value':round(formation_enthalpy[0]*H2eV,5),'error':round(formation_enthalpy[1]*H2eV,5)}
  else:
    formation_enthalpy = {'value':None,'error':None}
  attributes['infinite_limit'] = {'total_energy':y_int,'formation_enthalpy':formation_enthalpy}

  return render(request,'materialoverview.html',{'attributes':attributes,'chart':cht})
