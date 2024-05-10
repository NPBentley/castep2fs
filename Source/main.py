#!/usr/bin/env python3
import numpy as np
import sys,os
import pyvista as pv
import warnings
import time
import argparse
from colorsys import rgb_to_hsv, hsv_to_rgb
import ase.io as io
from Source import BZ
from Source import bands
#import BZ
#import bands  
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.pyplot as plt
from ase.spacegroup import Spacegroup
from itertools import cycle
from matplotlib import colors
from scipy.spatial import ConvexHull
from scipy.spatial.distance import pdist, squareform
from matplotlib.collections import LineCollection
from scipy.optimize import linprog
import matplotlib
from scipy.interpolate import interp2d,LinearNDInterpolator
matplotlib.rc('text', usetex = True)


matplotlib.rcParams['mathtext.fontset'] = 'stix'
matplotlib.rcParams['font.family'] = 'STIXGeneral'

def main():    

    warnings.filterwarnings("ignore")
    
    
    # Start with the parser
    parser = argparse.ArgumentParser(description= "Visualisation of Brillouin zone and fermi surfaces for DFT calculations performed in the CASTEP code.")
    parser.add_argument("seed",help="The seed from the CASTEP calculation.")
    
    parser.add_argument("--save",help="Save image of BZ.",action="store_true")
    #parser.add_argument("-l","--labels",help="Turn on special labels",action="store_true")
    #parser.add_argument("--paths",help="Turn on special paths",action="store_true")
    parser.add_argument("-fs","--fermi",help="Suppress plot the of Fermi surface from a DOS .bands",action="store_false")
    parser.add_argument("-c","--colour",help="Matplotlib colourmap for surface colouring",default='viridis')#,default="default")
    parser.add_argument("--show",help="Choose which spin channels to plot.",choices=['both','up','down'],default="both")
    parser.add_argument("--nsurf",help="Choose which surfaces to plot, 0 indexed.",nargs="+")
    parser.add_argument("-p","--primitive",help="Display the primitive cell",action="store_true")
    parser.add_argument("-s","--smooth",help="Smoothing factor for Fermi surfaces",default=10,type=int)
    parser.add_argument("-v","--velocity",help="Colour Fermi Surfaces by Fermi Velocity",action="store_true")
    parser.add_argument("-m","--mass",help="Colour Fermi Surfaces by effective mass",action="store_true")
    parser.add_argument("-o","--opacity",help="Opacity of Fermi Surfaces",default=[1],type=float,nargs="+")
    parser.add_argument("--verbose",help="Set print verbosity",action="store_true")
    parser.add_argument("-z","--zoom",help="Zoom multiplier",default=1)
    parser.add_argument("-P","--position",help="Camera position vector, 6 arguments required in order given by 'verbose' output",nargs=6,default=np.array([0.,0.,0.,0.,0.,0.]),type=float)
    parser.add_argument("-f","--faces",help="Show faces surounding the Brillouin zone.", action="store_true")
    parser.add_argument("-B","--background",help="Background colour of plotting environment",default="Document",choices=["Document","ParaView","night","default"])
    parser.add_argument("-O","--offset",help="Fermi surface isovalue offset in eV",default=0.0,type=float)
    parser.add_argument("-a","--axes",help="Toggle axes visability",action="store_false")
    parser.add_argument("--axis_labels",help="Toggle axes labels, only visible when showing axes",action="store_false")
    parser.add_argument("--pdos",help="Use .pdos_bin to color fermi surface",action="store_true")
    parser.add_argument("--species",help="Project pdos onto species rather than orbitals",action='store_true')
    parser.add_argument("--gif",help="Option to generate an orbital .gif",action='store_true')
    parser.add_argument("-d",'--dryrun',help='Fermi surface analysis without displaying results',action="store_true")
    parser.add_argument('--slice',help="Plane to plot slice through",nargs=3,type=int)
    parser.add_argument('-r','--rotation',help='Overide for plotting slices to improve appearence (deg)',default=0,type=float)
    parser.add_argument('--holes',help='Calculate electron and hole orbits. Red/Blue for electron/holes',action="store_true")
    parser.add_argument('--super',help='Display a supercell of the primitive Brillouin zone',type=int, nargs=3)
    parser.add_argument('--path',help='Visualise a path in a BZ',nargs="*")
    parser.add_argument('--orient',choices=['kx','ky','kz'],default=None)
    parser.add_argument('--spin',help='Colour the surfaces by the spin-channel (red=up, blue=down)',action='store_true')
    args = parser.parse_args()
    seed=args.seed
    save=args.save
    #plot_paths=args.paths
    #plot_labels=args.labels
    fermi=args.fermi
    col=args.colour
    start_time = time.time()
    show=args.show
    n_surf=args.nsurf
    prim=args.primitive
    smooth=args.smooth
    velocity=args.velocity
    mass=args.mass
    opacity=args.opacity
    verbose=args.verbose
    cam_pos=args.position
    show_faces=args.faces
    background=args.background
    z=np.float64(args.zoom)
    offset=args.offset
    show_axes=args.axes
    show_labels=args.axis_labels
    pdos=args.pdos
    species=args.species
    gif=args.gif
    dry=args.dryrun
    theta=args.rotation
    theta=np.deg2rad(theta)
    holes=args.holes
    supercell=args.super
    path=args.path
    c, s = np.cos(theta), np.sin(theta)
    R_corr = np.array(((c, -s, 0), (s, c, 0),(0,0,1)))
    orient=args.orient
    color_spin=args.spin
    slice=args.slice
    if slice!=None:
        plot_slice=True
        
    else:
        plot_slice=False

    
    if not show_axes:
        show_labels=False



    def pdos_read(seed,species,bs):
        from scipy.io import FortranFile as FF

        f=FF(seed+'.pdos_bin', 'r','>u4')
        
        version=f.read_reals('>f8')
        header=f.read_record('a80')[0]
        num_kpoints=f.read_ints('>u4')[0]
        num_spins=f.read_ints('>u4')[0]
        num_popn_orb=f.read_ints('>u4')[0]
        max_eigenvalues=f.read_ints('>u4')[0]
        
        orbital_species=f.read_ints('>u4')
        orbital_ion=f.read_ints('>u4')
        orbital_l=f.read_ints('>u4')
        
        kpoints=np.zeros((num_kpoints,3))
        pdos_weights=np.zeros((num_popn_orb,max_eigenvalues,num_kpoints,num_spins))
        for nk in range(0,num_kpoints):
            record=f.read_record('>i4','>3f8')
            kpt_index,kpoints[nk,:]=record
            for ns in range(0,num_spins):
                spin_index=f.read_ints('>u4')[0]
                num_eigenvalues=f.read_ints('>u4')[0]
                
                for nb in range(0,num_eigenvalues):
                    pdos_weights[0:num_popn_orb,nb,nk,ns]=f.read_reals('>f8')
                    
                    #norm=np.sqrt(np.sum((pdos_weights[0:num_popn_orb,nb,nk,ns])**2))
                    norm=np.sum((pdos_weights[0:num_popn_orb,nb,nk,ns]))
                    pdos_weights[0:num_popn_orb,nb,nk,ns]=pdos_weights[0:num_popn_orb,nb,nk,ns]/norm
                    
        if species:
            num_species=len(np.unique(orbital_species))
            pdos_weights_sum=np.zeros((num_species,max_eigenvalues,num_kpoints,num_spins))
            
            for i in range(0,num_species):
                loc=np.where(orbital_species==i+1)[0]
                pdos_weights_sum[i,:,:,:]=np.sum(pdos_weights[loc,:,:,:],axis=0)
            pdos_weights_reorder=np.zeros((num_species,max_eigenvalues,len(bs.kpoints),num_spins))                        
            
        else:
            num_orbitals=4
            pdos_weights_sum=np.zeros((num_orbitals,max_eigenvalues,num_kpoints,num_spins))
            pdos_colours=np.zeros((3,max_eigenvalues,num_kpoints,num_spins))
            
            r=np.array([1,0,0])
            g=np.array([0,1,0])
            b=np.array([0,0,1])
            k=np.array([0,0,0])
            
            
            
            for i in range(0,num_orbitals):
                loc=np.where(orbital_l==i)[0]
                if len(loc)>0:
                
                    pdos_weights_sum[i,:,:,:]=np.sum(pdos_weights[loc,:,:,:],axis=0)
            pdos_weights_reorder=np.zeros((num_orbitals,max_eigenvalues,len(bs.kpoints),num_spins))                        


        pdos_weights_sum=np.where(pdos_weights_sum>1,1,pdos_weights_sum)
        pdos_weights_sum=np.where(pdos_weights_sum<0,0,pdos_weights_sum)

        # reorder the thing


        for kp in range(len(bs.kpoints)):
            pdos_weights_reorder[:,:,kp,:]=pdos_weights_sum[:,:,bs.kpoint_map[kp],:]


        pdos_weights=np.zeros((max_eigenvalues,len(kpoints),num_spins))
        for kp in range(len(kpoints)):
            for n in range(max_eigenvalues):        
                for s in range(num_spins):
                    #print(pdos_weights_sum.shape,n,kp,s,len(kpoints))
                    max_l=np.where(pdos_weights_sum[:,n,kp,s]==np.max(pdos_weights_sum[:,n,kp,s]))[0]
                    #print(max_l)

                    pdos_weights[n,kp,s]=max_l
                    
        return np.round(pdos_weights_reorder,13),kpoints,pdos_weights

    
    
    line_color="black"
    face_op=0.5#opacity[0]
    if opacity==1:
        opacity=[1]
    if background=="default" or background =="night" or background=="ParaView":
        line_color="white"
    #if (opacity>1).any() or (opacity<0).any():
    #    print("\u001b[31mError: Invalid opacity\u001b[0m")
    #    sys.exit()
    
    # Aux functions
    def blockPrint():
        sys.stdout = open(os.devnull, 'w')
    def enablePrint():
        sys.stdout = sys.__stdout__
    
    
    def castep_read_out_sym(seed):
    
        out_cell=open(seed+"-out.cell","r")
        out_lines=out_cell.readlines()
        spec_grid=[1,1,1]
        for i in range(len(out_lines)):
            if "%BLOCK symmetry_ops" in out_lines[i]:
                start_line=i
            if "%ENDBLOCK symmetry_ops" in out_lines[i]:
                end_line=i
            if "spectral_kpoint_mp_grid" in out_lines[i] or "bs_kpoint_mp_grid" in out_lines[i]:
                spec_grid=np.array(out_lines[i].split()[-3:],dtype=float)
    
        n_ops=int((end_line-start_line-1)/5)
        rotations=np.zeros((n_ops,3,3))
        translations=np.zeros((n_ops,3))
    
        for i in range(n_ops):
            rotations[i,:,0]=[float(j) for j in out_lines[start_line+2+i*5].split()]
            rotations[i,:,1]=[float(j) for j in out_lines[start_line+3+i*5].split()]
            rotations[i,:,2]=[float(j) for j in out_lines[start_line+4+i*5].split()]
            translations[i,:]=[float(j) for j in out_lines[start_line+5+i*5].split()]
    
        return rotations,translations,spec_grid

    def skew(x):
        return np.array([[0, -x[2], x[1]],
                         [x[2], 0, -x[0]],
                         [-x[1], x[0], 0]])

    def trans(mesh,rgb=False,cmap=None,scalars=None,scale_bar=False,color=c):
        
        for i in range(0,supercell[0]):
            for j in range(0,supercell[1]):
                for k in range(0,supercell[2]):
                    if supercell[0]%2==0:
                        i_t=i-((supercell[0]/2)-1)
                    else:
                        i_t=i-((supercell[0]-1)/2)
                    if supercell[1]%2==0:
                        j_t=j-((supercell[1]/2)-1)
                    else:
                        j_t=j-((supercell[1]-1)/2)
                    if supercell[2]%2==0:
                        k_t=k-((supercell[2]/2)-1)
                    else:
                        k_t=k-((supercell[2]-1)/2)                                            
                        
                    T=i_t*recip_latt[0]+j_t*recip_latt[1]+k_t*recip_latt[2]
                    
                    matrix=np.array([[1,0,0,T[0]],
                                     [0,1,0,T[1]],
                                     [0,0,1,T[2]],
                                     [0,0,0,1]])
                    translated=mesh.transform(matrix,inplace=False)
                    
                    p.add_mesh(translated,rgb=rgb,scalars=scalars,color=c,smooth_shading=True,show_scalar_bar = scale_bar,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)

                    

    def mask_outside_polygon(poly_verts, ax=None):
        """
        Plots a mask on the specified axis ("ax", defaults to plt.gca()) such that
        all areas outside of the polygon specified by "poly_verts" are masked.  
        
        "poly_verts" must be a list of tuples of the verticies in the polygon in
        counter-clockwise order.
        
        Returns the matplotlib.patches.PathPatch instance plotted on the figure.
        """
        import matplotlib.patches as mpatches
        import matplotlib.path as mpath
        
        if ax is None:
            ax = plt.gca()
            
        # Get current plot limits
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        
        # Verticies of the plot boundaries in clockwise order
        bound_verts = [(xlim[0], ylim[0]), (xlim[0], ylim[1]), 
                       (xlim[1], ylim[1]), (xlim[1], ylim[0]), 
                       (xlim[0], ylim[0])]
        
        # A series of codes (1 and 2) to tell matplotlib whether to draw a line or 
        # move the "pen" (So that there's no connecting line)
        bound_codes = [mpath.Path.MOVETO] + (len(bound_verts) - 1) * [mpath.Path.LINETO]
        poly_codes = [mpath.Path.MOVETO] + (len(poly_verts) - 1) * [mpath.Path.LINETO]
        
        # Plot the masking patch
        path = mpath.Path(bound_verts + poly_verts, bound_codes + poly_codes)
        patch = mpatches.PathPatch(path, facecolor='white', edgecolor='none')
        patch = ax.add_patch(patch)
        
        # Reset the plot limits to their original extents
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        
        return patch


    
    colours=cycle(("blue",'yellow','purple','pink','green','orange'))
    colours=cycle(('#0081a7','#eb8258','#f6f740','#3cdbd3','#e3d7ff'))
    opacity=cycle(opacity)
    if plot_slice and col=='black':
        colours=cycle(('black'))

    #colours=cycle(("FC9E4F",'4A0D67','50514F','59FFA0','FF8CC6'))
    if col!="default":
        if col=="black":
            colours=cycle(('black','black','black','black','black'))

        else:
            cmap=plt.get_cmap(col)
            colours=cycle(cmap(np.linspace(0.1,1,5)))
        
    else:
        col="rainbow"
    
    #Open the files: Cell and bands
    blockPrint()
    try:
        cell=io.read(seed+".cell")
    except:
        raise Exception("No file "+seed+".cell")
    
    
    enablePrint()
    positions=cell.get_positions()
    numbers=cell.get_atomic_numbers()
    latt=cell.get_cell()
    atoms=np.unique(cell.get_chemical_symbols())[::-1]
    # Get the BZ information
    bril_zone=BZ.BZ(cell)
    recip_latt=bril_zone.recip_latt
    
    if species:
        n_cat=len(atoms)
    else:
        n_cat=4
        
    # Try and read a castep <seed>-out.cell, if not will have to use the ase symmetries
    try:
        symmetry=castep_read_out_sym(seed)
    except:
        print("Can't find <seed>-out.cell, proceeding with ASE, results may be inaccuracte")
        spacegroup=Spacegroup(bril_zone.sg)
        rot,trans=spacegroup.get_op()
        symmetry=(rot,trans,[1,1,1])
    
    
    # Get the bands information if needed
    if fermi:
        bs=bands.BandStructure(seed,recip_latt,np.array(latt),bril_zone.bz_vert,symmetry,prim,supercell,offset)

    
    # Set up the plotting stuff
    pv.set_plot_theme(background)
    
    
    if save:
        p=pv.Plotter(off_screen=True,lighting="three lights")
    else:
        p = pv.Plotter(lighting="three lights")
    p.enable_parallel_projection()
    
    
    #light = pv.Light()
    #light.set_direction_angle(30, 0)
    specular_power=30
    specular=2
    ambient=0.3
    diffuse=00.55
    

    # Run the pdos if needed
    if pdos:
        pdos_weights,full_kp,pdos_norm=pdos_read(seed,species,bs)
    
    # Add box for BZ
    if not prim:
        for i in range(len(bril_zone.edges)):
            if not save:
                p.add_lines(bril_zone.edges[i],color=line_color,width=1.5)
            else:
                p.add_lines(bril_zone.edges[i],color=line_color,width=10.5)
    
    # Add prim box if wanted    
    edges  = np.array([[[0.,0.,0.],[0.,0.,1.]],
    		   [[0.,0.,0.],[0.,1.,0.]],
                       [[0.,0.,0.],[1.,0.,0.]],
    	           [[1.,1.,1.],[1.,0.,1.]],
                       [[1.,1.,1.],[1.,1.,0.]],
    	           [[1.,1.,1.],[0.,1.,1.]],
    	           [[0.,1.,1.],[0.,0.,1.]],
                       [[0.,1.,1.],[0.,1.,0.]],
                       [[1.,1.,0.],[1.,0.,0.]],
                       [[1.,1.,0.],[0.,1.,0.]],
    		   [[1.,0.,0.],[1.,0.,1.]],
    		   [[0.,0.,1.],[1.,0.,1.]]])
    
    prim_vert=np.array([[0,0,0],   # 0 0
                        [1,0,0],   # 1 1
                        [0,1,0],   # 3 2
                        [1,1,0],   # 2 3
                        [0,0,1],   # 4 4
                        [1,0,1],   # 5 5
                        [0,1,1],   # 7 6
                        [1,1,1]],dtype=float)  # 6 7
    prim_faces=np.hstack([[4,0,2,3,1], # bottom /
                          [4,0,1,5,4], # front / 
                          [4,0,2,6,4], # left /
                          [4,4,5,7,6], # top   /
                          [4,1,3,7,5], # right /
                          [4,2,3,7,6]]) # back /
    
    for i,main in enumerate(edges):
        for j,sub in enumerate(main):
            edges[i,j]=np.matmul(recip_latt.T,sub)
    
    if prim:
        for i in range(0,12):
            if not save:
                p.add_lines(edges[i],width=1.5,color=line_color)
            else:
                p.add_lines(edges[i],width=2.5,color=line_color)
    
    # mesh edges for making a boundary surface
    if prim:
        verts=np.append(edges[:,0],edges[:,1],axis=0)
        for i in range(len(prim_vert)):
            prim_vert[i]=np.matmul(recip_latt.T,prim_vert[i])
            
            verts=pv.PolyData(prim_vert,prim_faces)
    else:
        verts=np.append(bril_zone.edges[:,0],bril_zone.edges[:,1],axis=0)
        verts=np.round(verts,9)
        verts=np.unique(verts,axis=0)

        outer=bril_zone.bz_vert
        faces=[]

        for f in range(len(outer)):
            v_face=outer[f][0]
            faces.append(len(v_face))
            for i in range(len(v_face)):
                for j in range(len(verts)):
                    if np.allclose(verts[j],v_face[i]):
                        faces.append(j)
                        

        
        verts=pv.PolyData(verts,faces)



    # Add recip lattice vecs
    #axis_lab=np.array(["$k_x$","$k_y$","$k_z$"])
    #print("test")
    axis_lab=np.array([r"k1","k2","k3"])
    min_k=np.max(np.linalg.norm(recip_latt,axis=1))
    l=np.zeros((3))
    recip_latt_labels = recip_latt
    arrow_scale=np.array([0.2,0.2,0.2])
    if show_axes:
        for i in range(0,3):
            l[i]=np.linalg.norm(recip_latt[i])
            
            r=min_k/l[i]
            arrow=pv.Arrow([0.2,0,0],0.25*recip_latt[i]*(arrow_scale[i]/l[i]),shaft_radius=0.015,tip_radius=0.05,tip_length=0.25,scale="auto")
            p.add_mesh(arrow,color="black")
            recip_latt_labels[i] = recip_latt_labels[i]*(arrow_scale[i]/l[i]) 
        if show_labels:
            if not save:
                p.add_point_labels(0.3*recip_latt_labels+[0.21,0,-0.005],axis_lab,shape=None,always_visible=True,show_points=False,font_family="courier",font_size=24,italic=True)
            else:
                p.add_point_labels(0.35*recip_latt_labels+[0.21,0,-0.01],axis_lab,shape=None,always_visible=True,show_points=False,font_family="times",font_size=120)
                
    
    #Special points labels
    from matplotlib import rcParams
    rcParams['text.usetex'] = True
    #p.add_point_labels(bril_zone.bz_points,bril_zone.bz_labels,shape=None,always_visible=True,show_points=True,font_size=24)

    # path points
    bv_latt=cell.cell.get_bravais_lattice()
    special_points=bv_latt.get_special_points()
    if path is not None:
        path_points=[]
        path_labels=[]
        
        for i in path:
            
            
            try:
                path_point=special_points[i]
                path_point=np.matmul(recip_latt.T,path_point)
                
                path_points.append(path_point)
                if i=='G':
                    path_labels.append(r'$\Gamma$')
                else:                
                    path_labels.append(i)
            except:
                print()
                print("Error: %s has no symmetry point %s"%(bv_latt.name,i))
                sys.exit()
                path_points.append(path_point)
                path_labels.append(i)
            
        for i in range(len(path_points)-1):
            line=pv.Line(path_points[i],path_points[i+1])
            p.add_mesh(line,color='red',line_width=5)
        p.add_point_labels(path_points,path_labels,shape=None,always_visible=True,show_points=False,font_family="courier",font_size=24,italic=True)
        print(path_points)



    
    #if plot_paths:
    #for i in range(len(bril_zone.bz_path)):
    #    p.add_lines(bril_zone.bz_path[i],color="red",width=1.5)
    
    # Check if we are metallic in any channel
    if fermi:
        fermi=bs.metal
        if not bs.metal:
            print('\033[93m Material is insulating, no Fermi surfaces to display.  \u001b[0m')

            
    if fermi:
        point_cloud = pv.PolyData(bs.kpoints)
        #point_cloud = pv.PolyData(bs.kpt_irr)

        basis=[]
        n_colors=cycle(['#0000FF','#FF0000','#00FF00','yellow','purple','orange','black','cyan'])
        #n_colors=cycle(['#0000FF','#FF0000','cyan','yellow','purple','orange','black','cyan'])
        
        for n in range(n_cat):
            basis.append(np.array(colors.to_rgba(next(n_colors))))

        basis=np.array(basis).reshape((n_cat,4))

    
        # Get the kpoints
        kpoints=bs.kpoints

        # Check kpoint density
        if len(kpoints)<600 :
            print('\033[93m K-point density is relatively low, results may not be accurate..  \u001b[0m')
    
        
        # Calculate the spacing
        frac_spacing=1/np.array(symmetry[2])
        recip_spacing=np.matmul(recip_latt,frac_spacing)
        max_spacing=2*np.max(recip_spacing)
        if max_spacing>0.2:
            max_spacing=0.2
    
        #Number of fermi surfaces
            
        ids=bs.ids
        n_fermi=bs.n_fermi
        energy=bs.energy[:,:,:]        
        # Print the report
        print("+=========================================================+")
        print("| Electron   Spin   Min. (eV)  Max. (eV)   Bandwidth (eV) |")
        print("+=========================================================+")

        
        for i in range(n_fermi[0]):
            print("|    {:04d}      up     {:6.3f}     {:6.3f}         {:6.3f}    |".format(ids[i,0],np.min(energy[i,:,0]),np.max(energy[i,:,0]),(np.max(energy[i,:,0])-np.min(energy[i,:,0]))))
            
        if bs.nspins==2:
            for i in range(n_fermi[1]):
                print("|    {:04d}    down     {:6.3f}     {:6.3f}         {:6.3f}    |".format(ids[i,1],np.min(energy[i,:,1]),np.max(energy[i,:,1]),(np.max(energy[i,:,1])-np.min(energy[i,:,1]))))

                
        print("+=========================================================+")

        if pdos:
            
            print("|                        P D O S                          |")
            print("+=========================================================+")
            if species:
                print("|     Species                         RGB Colour          |")
                print("+=========================================================+")
                for i in range(n_cat):
                    print('|       %s:                       (%4.2f, %4.2f, %4.2f)      |'%(atoms[i],basis[i,0],basis[i,1],basis[i,2]))
                print("+=========================================================+")
            else:
                orbs=['s','p','d','f']
                print("|     Orbital                         RGB Colour          |")
                print("+=========================================================+")
                for i in range(n_cat):
                    print('|       %s :                       (%4.2f, %4.2f, %4.2f)      |'%(orbs[i],basis[i,0],basis[i,1],basis[i,2]))
                print("+=========================================================+")
             

            
        
        if dry:
            sys.exit()
        nspins=range(bs.nspins)
        
        if show=='down':
            nspins=[1]
        elif show=='up':
            nspins=[0]
            
        #If degenerate energies dont plot down spins, slow and not worth it!
        if bs.degen:
            nspins=[0]

        if plot_slice:

            fig = plt.figure(figsize=(9,9))
            ax = fig.add_subplot(111)
            ax.set_aspect('equal')
            
            # Calculte norm
            norm=slice[0]*recip_latt.T[:,0]+slice[1]*recip_latt.T[:,1]+slice[2]*recip_latt.T[:,2]
            norm=norm/np.linalg.norm(norm)
            
            v_R=np.cross(norm,np.array([0,0,1]))
            s_R=np.linalg.norm(v_R)
            c_R=np.dot(norm,np.array([0,0,1]))
            skew_R=skew(v_R)
            
            R=np.identity(3)+skew_R+np.dot(skew_R,skew_R)*(1-c_R)/(s_R**2)
            
            if (v_R==0).all():
                R=np.identity(3)
            
            # Calculate the rotation for prettyness (project kx onto plane and rotate to y)
            kx= recip_latt.T[:,0]/np.linalg.norm(recip_latt.T[:,0])
            plane_vec=np.matmul(R,kx-np.dot(kx,norm)*norm)

            if (slice==np.array([1,0,0])).all():
                direction=np.array([0,1,0])
            else:
                direction=np.array([1,0,0])
            
            v_P=np.cross(plane_vec,direction)
            s_P=np.linalg.norm(v_P)
            c_P=np.dot(plane_vec,direction)
            skew_P=skew(v_P)

            R_P=np.identity(3)+skew_P+np.dot(skew_P,skew_P)*(1-c_P)/(s_P**2)


            if (v_P==0).all() or abs(np.linalg.det(R_P))<0.001:

                R_P=np.identity(3)

            
            R=np.matmul(R_P,R)
            R=np.matmul(R_corr,R)
            

            plane=pv.Plane(center=[0,0,0],direction=norm)
            plane=plane.triangulate()

            border=verts.triangulate()
            border=border.intersection(plane)[0]

            outline=np.array(border.points)

            

            for i in range(len(outline)):
                outline[i]=np.matmul(R,outline[i])
                

            outline=outline[:,0:2]
            hull = ConvexHull(outline)
        
            ax.plot(outline[hull.vertices,0], outline[hull.vertices,1], 'k-', lw=2)
            outline=outline[hull.vertices,:]
            connect=outline[[0,-1]]
            ax.plot(connect[:,0],connect[:,1], 'k-', lw=2)
            ax.axis("off")
            ax.set_xlim(1.05*np.min(outline[:,0]),1.05*np.max(outline[:,0]))
            ax.set_ylim(1.05*np.min(outline[:,1]),1.05*np.max(outline[:,1]))

            #do the special point labels


            for li,L in enumerate(bril_zone.bz_points):

                if abs(np.linalg.norm(np.dot(norm,L)))<0.001:
                    
                    point=np.matmul(R,L)
                    ax.text(point[0],point[1],bril_zone.bz_labels[li],fontsize=22)
                    ax.scatter(point[0],point[1],marker='s',c='k',zorder=2)




        cloud=pv.PolyData(bs.kpoints)
            
        interp = cloud.delaunay_3d(alpha=100,progress_bar=verbose)
        total_vol=interp.volume

        for spin in nspins:

            #Extract all the right stuf


            
            # get the indices to plot
            if n_surf!=None:
                n_surf=np.array(n_surf,dtype=int)
            else:
                n_surf=range(np.max(n_fermi))

            for band in range(0,n_fermi[spin]):
                
                c=next(colours)

                #Change the colors
                if color_spin:
                    if spin==0:
                        c=[1.,0.,0.,1.]
                    elif spin==1:
                        c=[0.,0.,1.,1.]


                op=next(opacity)
                if band in n_surf:

                    interp.point_arrays["values"]=energy[band,:,spin]
                    if not plot_slice:
                        contours=interp.contour([offset],scalars="values")                
                        contours=contours.smooth(n_iter=smooth)

                    
                        if not prim:
                            for face in bril_zone.bz_vert:
                                origin=face[0][0]
                                direction=face[1]
                                contours=contours.clip(origin=origin,normal=direction)
                    
                        cont_vol=contours.volume
                        surf_vol=100*cont_vol/total_vol
                        if verbose:
                            print("%2d  up    %2.3f %% " %(band,surf_vol))


                        if surf_vol<5 and smooth>10:
                            print('\033[93m'+"Small Fermi surfaces may become distorted with large 'smooth' parameter, consider reducing.\u001b[0m")

                    if plot_slice:

                        p_slice=interp.slice(normal=norm).delaunay_2d()#.smooth(smooth)
                        p.add_mesh(p_slice)
                        val=np.array(p_slice['values'])
                        proj_points=np.array(p_slice.points)


                        for i in range(len(proj_points)):
                            proj_points[i]=np.matmul(R,proj_points[i])


                        proj_points=proj_points[:,0:2]
                        X,Y=proj_points[:,0],proj_points[:,1]
                        cmap=plt.get_cmap('viridis')

                        

                        f = LinearNDInterpolator(proj_points,val)

                        N=300                    
                        x_coords = np.linspace(np.min(outline),np.max(outline),N)
                        y_coords = np.linspace(np.min(outline),np.max(outline),N)

                        Z=np.ones((N,N))
                        for i in range(N):
                            for j in range(N):
                                Z[j,i]=f(x_coords[i],y_coords[j])

                        Z = np.nan_to_num(Z,nan=1)        
                        if holes:
                            order=0
                        else:
                            order=1
                        cs=ax.contour(x_coords,y_coords,Z,0,colors=c,zorder=order)
                        
                        '''
                        if holes:
                            
                            
                            grad=np.gradient(Z)
                            grad_x=np.gradient(grad[0])[0]
                            grad_y=np.gradient(grad[1])[1]
                            laplace=grad_x+grad_y
                            
                            k_origin=np.zeros((N*N,2))
                            laplace_flat=np.zeros((N*N))
                            v_mag=np.zeros((N*N,2))
                            o=0

                            for i in range(N):
                                for j in range(N):
                                    
                                    k_loc=np.array([x_coords[i],y_coords[j],0])
                                    vk=np.array([grad[0][i,j],grad[1][i,j],0])
                                    k_origin[o,:]=k_loc[0:2]
                                    v_mag[o,:]=vk[0:2]
                                    laplace_flat[o]=laplace[i,j]
                                    o+=1
                            ax.quiver(k_origin[:,1],k_origin[:,0],v_mag[:,1],v_mag[:,0])
                            f=LinearNDInterpolator(k_origin,laplace_flat)
                            for cont in cs.collections[1].get_paths():
                                path_points=cont.vertices
                                div=0
                                for v in range(len(path_points)):
                                    div+=f(path_points[v][0],path_points[v][1])
                                if div<0:
                                    elec_hole='blue'
                                else:
                                    elec_hole='red'
                                print(div)
                                ax.plot(path_points[:,0],path_points[:,1],color=elec_hole,zorder=0)
                           '''     
                    elif holes:
                        grad=interp.compute_derivative(scalars="values")
                        grad=grad.compute_derivative(scalars='gradient',divergence=True)
                        #grad['divergence']=np.sign(grad['divergence'])
                        contours=contours.interpolate(grad,radius=max_spacing)
                        div=np.sum(contours['divergence'])

                        if div<0:
                            #hole
                            elec_hole='blue'
                        else:
                            #electron
                            elec_hole='red'
                        if supercell!=None:
                            trans(contours,color=elec_hole)
                        else:
                            p.add_mesh(contours,color=elec_hole,smooth_shading=True,show_scalar_bar=False,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)
                        

                    elif velocity:

                        grad=interp.compute_derivative(scalars="values")
                        grad['Fermi Velocity (m/s)']=np.sqrt(np.sum(grad['gradient']**2,axis=1))*1.6e-19*1e-10/(1.05e-34)

                        std=np.std(grad['Fermi Velocity (m/s)'])
                        mean=np.mean(grad['Fermi Velocity (m/s)'])
                        above=np.where(grad['Fermi Velocity (m/s)']>mean+1*std)[0]
                        grad['Fermi Velocity (m/s)'][above]=0#mean+1*std
                        contours=contours.interpolate(grad,radius=max_spacing)

                        if supercell!=None:
                            trans(contours,scalars="Fermi Velocity (m/s)",cmap=col,scale_bar=True)
                        
                        else:
                            p.add_mesh(contours,scalars="Fermi Velocity (m/s)",cmap=col,smooth_shading=True,show_scalar_bar=True,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)
                    #elif mass:
                    #    grad=interp.compute_derivative(scalars="values")
                    #    grad2=grad.compute_derivative(scalars="gradient")
                    #    grad2['Effective Mass']=grad2['gradient']#np.sqrt(np.sum(grad['gradient']**2,axis=1))*1.6e-19*1e-10/(1.05e-34)

                        #std=np.std(grad['Fermi Velocity (m/s)'])
                        #mean=np.mean(grad['Fermi Velocity (m/s)'])
                        #above=np.where(grad['Fermi Velocity (m/s)']>mean+1*std)[0]
                        #grad['Fermi Velocity (m/s)'][above]=0#mean+1*std
                        #contours=contours.interpolate(grad2,radius=max_spacing)
                        
                        #p.add_mesh(contours,scalars="Effective Mass",cmap=col,smooth_shading=True,show_scalar_bar=True,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)
                        
                    elif pdos:
                        cmap_array=np.zeros((len(kpoints),4))
                        kpoint_pick=924

                        for n in range(n_cat):
                            cmap_array[:,0]+=pdos_weights[n,ids[band,spin],:,0]*basis[n,0]
                            cmap_array[:,1]+=pdos_weights[n,ids[band,spin],:,0]*basis[n,1]
                            cmap_array[:,2]+=pdos_weights[n,ids[band,spin],:,0]*basis[n,2]

                            
                        
                        cmap_array[:,3]=1
                        max=np.max(cmap_array[:,0:3],axis=1)
                        max_array=np.zeros((len(kpoints),3))
                        max_array[:,0]=max
                        max_array[:,1]=max
                        max_array[:,2]=max
                        #cmap_array[:,0:3]=cmap_array[:,0:3]/max_array
                        
                        cmap_array=np.where(cmap_array>1,1,cmap_array)


                        interp.point_arrays["pdos"]=cmap_array
                        

                        #for kpoint_pick in range(0,len(kpoints),5):
                        #print("PDOS:",pdos_weights[:,ids[band,spin],kpoint_pick,spin])
                        #print("CMAP_ARRAY:",cmap_array[kpoint_pick])
                        #print("z:",z[kpoint_pick])
                        #print(cmap(z[kpoint_pick]))
                        #print()
                        #p.add_mesh(pv.Sphere(0.01,kpoints[kpoint_pick]),color=cmap(z[kpoint_pick])) 
                        
                        #sys.exit()
                        
                        contours=interp.contour([offset],scalars="values")
                        contours=contours.smooth(n_iter=smooth)
                        if not prim:
                            for face in bril_zone.bz_vert:
                                origin=face[0][0]
                                direction=face[1]
                                contours=contours.clip(origin=origin,normal=direction)
                        clim=100*[np.min(contours['pdos']),np.max(contours['pdos'])]
                                
                                
                        #p.add_mesh(contours,scalars="pdos",clim=clim,cmap=cmap,smooth_shading=True,show_scalar_bar = True,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)
                        if  supercell!=None:

                            trans(contours,rgb=True,scalars='pdos')
                        else:
                            p.add_mesh(contours,scalars='pdos',rgb=True,smooth_shading=True,show_scalar_bar = False,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)
                        #p.add_mesh(contours,scalars="pdos",cmap='Oranges',smooth_shading=True,show_scalar_bar = True,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)

                        
                        #p.add_mesh_slice(interp,show_scalar_bar=False,cmap='Oranges',show_edges=False,implicit=False)
                        
                    else:
                        if  supercell!=None:
                            trans(contours)
                        else:

                            p.add_mesh(contours,color=c[0:3],smooth_shading=True,show_scalar_bar = False,lighting=True,pickable=False,specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,opacity=op)

    
    p.window_size = 1000, 1000
    
    if prim:
        focus=np.matmul(recip_latt.T,[0.5,0.5,0.5])
    else:
        focus=[0,0,0]
    if show_faces:
        #p.add_mesh(verts)
        p.add_mesh(verts,opacity=face_op,color="grey",specular=specular,specular_power=specular_power,ambient=ambient,diffuse=diffuse,lighting=True)

    p.set_focus(focus)
    p.view_isometric()
    
    def button_a():
        o=recip_latt[2]
        vpvec=recip_latt[0]/np.linalg.norm(recip_latt[0])    
        vp=focus+15*vpvec
        p.camera_position=[vp,focus,o]
        
        
    def button_b():
        
        o=recip_latt[2]
        vpvec=recip_latt[1]/np.linalg.norm(recip_latt[1])
        vp=focus+15*vpvec
        p.camera_position=[vp,focus,o]
        
        
    def button_c():
        
        o=recip_latt[1]
        vpvec=recip_latt[2]/np.linalg.norm(recip_latt[2])
        
        vp=focus+15*vpvec
        p.camera_position=[vp,focus,o]
    
    def button_sd():
        o=recip_latt[2]
        T=0.9*recip_latt[0]+0.4*recip_latt[1]+0.6*recip_latt[2]
        vpvec=T/np.linalg.norm(T)
        vp=focus+15*vpvec
        p.camera_position=[vp,focus,o]
    p.add_key_event("a",button_a)
    p.add_key_event("b",button_b)
    p.add_key_event("c",button_c)
    p.add_key_event("o",button_sd)

    if not prim:
        o=recip_latt[2]
        T=0.9*recip_latt[0]+0.4*recip_latt[1]+0.6*recip_latt[2]
        vpvec=T/np.linalg.norm(T)
        vp=focus+100*vpvec
        #p.camera_position=[vp,focus,o]
        if orient != None:
            
            if orient=='kx':
                o=recip_latt[2]
                T=recip_latt[0]
                vpvec=T/np.linalg.norm(T)
            elif orient=='ky':
                o=recip_latt[2]
                T=recip_latt[1]
                vpvec=T/np.linalg.norm(T)            
            elif orient=='kz':
                o=recip_latt[1]
                T=recip_latt[2]
                vpvec=T/np.linalg.norm(T)            


            vp=focus+100*vpvec

            p.camera_position=[vp,focus,o]

    if np.sum(cam_pos)!=0:
        vp=(cam_pos[0],cam_pos[1],cam_pos[2])
        o=(cam_pos[3],cam_pos[4],cam_pos[5])
        p.camera_position=[vp,focus,o]
    try:
        p.camera.zoom(z)
    except:
        print("Zoom not implemented in this version of PyVista.")

    
    
    
    end_time=time.time()-start_time
    print("Time %3.3f s"%end_time)

    if plot_slice:
        mask_outside_polygon(list(outline),ax)
        if save:
            plt.savefig(seed+"_slice_%i_%i_%i.png"%(slice[0],slice[1],slice[2]))
        else:
            plt.show(block=True)
        
    else:
        if save:
            p.ren_win.SetOffScreenRendering(1)
            p.window_size=[3000,3000]

            p.show(title=seed,screenshot=seed+"_BZ.png")
        else:
            p.show(title=seed,auto_close=False)
            
        if verbose:
            print("Final Camera Position:")
            print(p.camera_position[0][0],p.camera_position[0][1],p.camera_position[0][2],p.camera_position[2][0],p.camera_position[2][1],p.camera_position[2][2])

        #path = p.generate_orbital_path(factor=2.0, shift=10000, viewup=viewup, n_points=36)
        #p.open_gif("orbit.gif")
        #p.orbit_on_path(path, write_frames=True, viewup=[0, 0, 1])
        if gif:
            gif_time=time.time()
            print("Writing movie to %s.gif..."%seed)
            
            path = p.generate_orbital_path(n_points=50, shift=0,viewup=vp)
            
            p.open_gif(seed+".gif")
            p.orbit_on_path(path, write_frames=True,focus=focus)
            p.close()
            movie_time=time.time()-gif_time
            print("Export time %3.3f s"%movie_time)
if __name__=='__main__':
    main()
