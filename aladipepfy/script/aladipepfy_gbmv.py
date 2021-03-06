# This script implements that c37test/domdec_gpu.inp test caseThis script generates and
# plots the alanine dipeptide phi/psi (f/y) map using pyCHARMM
# Written by C.L. Brooks III, November 10, 2020

import os
import sys
import subprocess
import numpy as np
import pandas as pd
import shlex

import pycharmm
import pycharmm.generate as gen
import pycharmm.ic as ic
import pycharmm.coor as coor
import pycharmm.energy as energy
import pycharmm.dynamics as dyn
import pycharmm.nbonds as nbonds
import pycharmm.minimize as minimize
# using lingo as stream
import pycharmm.lingo as stream
import pycharmm.crystal as crystal
import pycharmm.select as select
import pycharmm.image as image
import pycharmm.psf as psf
import pycharmm.param as param
import pycharmm.read as read
import pycharmm.write as write
import pycharmm.settings as settings
import pycharmm.cons_harm as cons_harm
import pycharmm.cons_fix as cons_fix
import pycharmm.shake as shake
import pycharmm.scalar as scalar

# Now we will loop over beads, w/ each bead assigned to
# a a computational node, where node = rank in python mpi
# set up a communicator and get the rank of this process
# Global variables
# Add in mpi support
from mpi4py import MPI
comm = MPI.COMM_WORLD
nproc = comm.Get_size()
rank = comm.Get_rank()

#####################################################################
def pltFYMap(F,Y,fymap):
    # reshape the energy array into nxn array
    # use transpose (.T) because of loop order above
    ener = np.reshape(np.asarray(fymap['ener']),(len(F),len(Y)))
    ener = ener.T
    # Make file and save on disk
    fymap = {'F':F,
             'Y':Y,
             'ener':ener}
    import pickle
    with open('maps/fymap-ala_gbmv.pkl', 'wb') as fh:
        pickle.dump(fymap, fh)
    with open('maps/fymap-ala_gbmv.pkl', 'rb') as fh:
        fymap = pickle.load(fh)

    emax = np.max(ener)
    emin = np.min(ener)
    erange = emax - emin
    ehigh = np.ceil(emin+1.1*erange)
    elow = np.floor(emax-1.1*erange)
    F,Y=np.meshgrid(F,Y)
    # Now let's plot the data f/y map
    from mpl_toolkits.mplot3d import axes3d
    import matplotlib.pyplot as plt
    from matplotlib import cm
    fig = plt.figure()
    ax = fig.gca(projection='3d')
    # Plot the 3D surface
    ax.contour3D(F,Y,ener,50,cmap='inferno')
    #ax.plot_surface(F, Y, ener, rstride=8, cstride=8, alpha=0.3)
    # Plot projections of the contours for each dimension.  By choosing offsets
    # that match the appropriate axes limits, the projected contours will sit on
    # the 'walls' of the graph
    #cset = ax.contour(F, Y, ener, zdir='ener', offset=elow, cmap=cm.coolwarm)
    #cset = ax.contour(F, Y, ener, zdir='f', offset=180, cmap=cm.coolwarm)
    #cset = ax.contour(F, Y, ener, zdir='y', offset=-180, cmap=cm.coolwarm)
    
    ax.set_xlim(-180, 180)
    ax.set_ylim(-180, 180)
    ax.set_zlim(elow, ehigh)
    
    ax.set_xlabel('Phi')
    ax.set_ylabel('Psi')
    ax.set_zlabel('E')
    plt.savefig('fysurf-ala_gbmv.pdf')    
    plt.show()
    fig = plt.figure(figsize=(12,10))
    left, bottom, width, height = 0.1, 0.1, 0.8, 0.8
    ax = fig.add_axes([left, bottom, width, height]) 
    cp = plt.contourf(F, Y, ener)
    plt.colorbar(cp)
    ax.set_title('Contour Plot')
    ax.set_xlabel('Phi')
    ax.set_ylabel('Psi')
    plt.savefig('fycontour-ala_gbmv.pdf')
    plt.show()
    return
#####################################################################
###############PYCHARMM SCRIPTING STARTS HERE########################
# template for f/y restraints
#Fcons = '1 clp 1 nl 1 ca 1 crp' # for alad residue
#Ycons = '1 nl 1 ca 1 crp 1 nr'  # for alad residue
Fcons = '1 cy 1 n 1 ca 1 c'
Ycons = '1 n 1 ca 1 c 1 nt'
read.rtf('toppar/top_all36_prot.rtf')
read.prm('toppar/par_all36_prot.prm')
read.sequence_string('ALA')  # ALAD for full dipeptide
gen.new_segment(seg_name='ALAD',
                first_patch='ACE', #comment to use alad residue
                last_patch='CT3',  #comment to use alad residue
                setup_ic=True)
ic.prm_fill(replace_all=True)
#ic.seed(1,'CL',1,'CLP',1,'NL')  #use for residue alad
ic.seed(1,'CAY',1,'CY',1,'N')  
ic.build()
print(coor.get_positions())
nbonds.configure({'cutnb': 16,
                  'ctofnb': 14,
                  'ctonnb': 12,
                  'atom': True,
                  'vatom': True,
                  'eps': 1,
                  'fswitch': True,
                  'vfswitch': True,
                  'cdie': True})
stream.charmm_script('nbonds switch vswitch')

minimize.run_abnr({'nstep': 1000,
                         'tolenr': 1e-3,
                         'tolgrd': 1e-3}, dict())

comm.barrier()
# set up phi/psi grid to apply restraints and
# compute energy
F = np.linspace(-180,180,36)
Y = F
fymap = {'F':[],
         'Y':[],
         'ener':[]}
for iphi,f in enumerate(F):
    if not ( iphi % nproc == rank ):
        continue
    for y in Y:
        # turn off noise
        settings.set_verbosity(0)
        settings.set_warn_level(-5)
        # Need to use stream here because no api for cons dihe
        cons = 'cons dihe {} force {} min {:4.2f}'.format(Fcons,500,f)
        stream.charmm_script(cons)
        cons = 'cons dihe {} force {} min {:4.2f}'.format(Ycons,500,y)
        stream.charmm_script(cons)
        minimize.run_abnr({'nstep': 1000,
                           'tolenr': 1e-3,
                           'tolgrd': 1e-3}, dict())
        gbmv_str = '''
prnlev 0
scalar wmain = radii
stream toppar/radii_c36gbmvop.str
prnlev 5
gbmv beta -12  p3 0.65 watr 1.4  shift -0.102 slope 0.9085 -
p6 8 sa 0.005 wtyp 2 nphi 38 cutnum 100 kappa 0 weight
        '''
        stream.charmm_script(gbmv_str)
        settings.set_verbosity(0)
        minimize.run_abnr({'nstep': 500,
                           'tolenr': 1e-3,
                           'tolgrd': 1e-3}, dict())

        stream.charmm_script('cons cldh')
        fymap['F'].append(f)
        fymap['Y'].append(y)
        fymap['ener'].append(energy.get_total())
        stream.charmm_script('gbmv clear')
    comm.barrier()
settings.set_verbosity(5)
comm.barrier()
for r in range(1,nproc):
    if rank == r:
        req = comm.isend(fymap,dest=0,tag=10+r)
        req.wait()
    elif rank == 0:
        req = comm.irecv(source=r,tag=10+r)
        t = req.wait()
        for k in t.keys():
            for i in t[k]: fymap[k].append(i)
    comm.barrier()
comm.barrier()
if rank == 0:
    en_df = pd.DataFrame.from_dict(fymap)
    en_df.sort_values(by=['F','Y'],inplace=True)
    fymap = en_df.to_dict(orient='list')
comm.barrier()
if rank == 0: pltFYMap(F,Y,fymap)
comm.barrier()
exit()
