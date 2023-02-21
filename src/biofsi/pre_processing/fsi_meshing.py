import argparse
import sys
from os import remove, path

import numpy as np
from morphman import is_surface_capped, get_uncapped_surface, write_polydata, get_parameters, vtk_clean_polydata, \
    vtk_triangulate_surface, write_parameters, vmtk_cap_polydata, compute_centerlines, get_centerline_tolerance, \
    get_vtk_point_locator, extract_single_line, vtk_merge_polydata, get_point_data_array, smooth_voronoi_diagram, \
    create_new_surface, compute_centers, vmtk_smooth_surface, str2bool, vmtk_compute_voronoi_diagram

from vampy.automatedPreprocessing import ToolRepairSTL
from vampy.automatedPreprocessing.preprocessing_common import read_polydata, get_centers_for_meshing, \
    get_regions_to_refine, add_flow_extension, \
    mesh_alternative, find_boundaries, \
    compute_flow_rate, setup_model_network, radiusArrayName

from vampy.automatedPreprocessing.visualize import visualize_model

from pre_processing_common import scale_surface, scale_mesh, refine_mesh_seed, generate_mesh_fsi, write_mesh

def str2bool(boolean):
    """Convert a string to boolean.
    Args:
        boolean (str): Input string.
    Returns:
        return (bool): Converted string.
    """
    if boolean.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif boolean.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise ValueError('Boolean value expected.')


def run_pre_processing(filename_model, verbose_print, smoothing_method, smoothing_factor, meshing_method,
                       refine_region, create_flow_extensions, viz, coarsening_factor,
                       inlet_flow_extension_length, outlet_flow_extension_length, edge_length, region_points,
                       compress_mesh, scale_factor):
    """
    Run the pre-processing steps for the FSI model.
    Args:
        filename_model (str): Path to the model file.
        verbose_print (bool): Print additional information.
        smoothing_method (str): Smoothing method to use.
        smoothing_factor (float): Smoothing factor.
        meshing_method (str): Meshing method to use.
        refine_region (bool): Refine the region around the centerline.
        create_flow_extensions (bool): Create flow extensions.
        viz (bool): Visualize the model.
        coarsening_factor (float): Coarsening factor.
        inlet_flow_extension_length (float): Length of the inlet flow extension.
        outlet_flow_extension_length (float): Length of the outlet flow extension.
        edge_length (float): Edge length.
        region_points (int): Position of the refinement region.
        compress_mesh (bool): Compress the mesh.
    Returns:
        None (volumential mesh is written to the same folder as the input model)
    """
    # Get paths
    abs_path = path.abspath(path.dirname(__file__))
    case_name = filename_model.rsplit(path.sep, 1)[-1].rsplit('.')[0]
    dir_path = filename_model.rsplit(path.sep, 1)[0]

    # Naming conventions
    file_name_centerlines = path.join(dir_path, case_name + "_centerlines.vtp")
    file_name_refine_region_centerlines = path.join(dir_path, case_name + "_refine_region_centerline.vtp")
    file_name_region_centerlines = path.join(dir_path, case_name + "_sac_centerline_{}.vtp")
    file_name_distance_to_sphere_diam = path.join(dir_path, case_name + "_distance_to_sphere_diam.vtp")
    file_name_distance_to_sphere_const = path.join(dir_path, case_name + "_distance_to_sphere_const.vtp")
    file_name_distance_to_sphere_curv = path.join(dir_path, case_name + "_distance_to_sphere_curv.vtp")
    file_name_probe_points = path.join(dir_path, case_name + "_probe_point")
    file_name_voronoi = path.join(dir_path, case_name + "_voronoi.vtp")
    file_name_voronoi_smooth = path.join(dir_path, case_name + "_voronoi_smooth.vtp")
    file_name_surface_smooth = path.join(dir_path, case_name + "_smooth.vtp")
    file_name_model_flow_ext = path.join(dir_path, case_name + "_flowext.vtp")
    file_name_clipped_model = path.join(dir_path, case_name + "_clippedmodel.vtp")
    file_name_flow_centerlines = path.join(dir_path, case_name + "_flow_cl.vtp")
    file_name_surface_name = path.join(dir_path, case_name + "_remeshed_surface.vtp")
    file_name_xml_mesh = path.join(dir_path, case_name + "_fsi.xml")
    file_name_vtu_mesh = path.join(dir_path, case_name + "_fsi.vtu")
    file_name_run_script = path.join(dir_path, case_name + ".sh")
    file_name_seedX = path.join(dir_path, case_name + "_seedX.vtp")

    print("\n--- Working on case:", case_name, "\n")

    # Open the surface file.
    print("--- Load model file\n")
    surface = read_polydata(filename_model)

    # Check if surface is closed and uncapps model if True
    if is_surface_capped(surface)[0] and smoothing_method != "voronoi":
        if not path.isfile(file_name_clipped_model):
            print("--- Clipping the models inlets and outlets.\n")
            # TODO: Add input parameters as input to automatedPreProcessing
            # Value of gradients_limit should be generally low, to detect flat surfaces corresponding
            # to closed boundaries. Area_limit will set an upper limit of the detected area, may vary between models.
            # The circleness_limit parameters determines the detected regions similarity to a circle, often assumed
            # to be close to a circle.
            surface = get_uncapped_surface(surface, gradients_limit=0.01, area_limit=20, circleness_limit=5)
            write_polydata(surface, file_name_clipped_model)
        else:
            surface = read_polydata(file_name_clipped_model)
    parameters = get_parameters(path.join(dir_path, case_name))

    if "check_surface" not in parameters.keys():
        surface = vtk_clean_polydata(surface)
        surface = vtk_triangulate_surface(surface)

        # Check the mesh if there is redundant nodes or NaN triangles.
        ToolRepairSTL.surfaceOverview(surface)
        ToolRepairSTL.foundAndDeleteNaNTriangles(surface)
        surface = ToolRepairSTL.cleanTheSurface(surface)
        foundNaN = ToolRepairSTL.foundAndDeleteNaNTriangles(surface)
        if foundNaN:
            raise RuntimeError(("There is an issue with the surface. "
                                "Nan coordinates or some other shenanigans."))
        else:
            parameters["check_surface"] = True
            write_parameters(parameters, path.join(dir_path, case_name))
        
    # Create a capped version of the surface
    capped_surface = vmtk_cap_polydata(surface)

    # Get centerlines
    print("--- Get centerlines\n")
    inlet, outlets = get_centers_for_meshing(surface, False, path.join(dir_path, case_name))
    source = inlet
    target = outlets

    centerlines, _, _ = compute_centerlines(source, target, file_name_centerlines, capped_surface, resampling=0.1)
    tol = get_centerline_tolerance(centerlines)

    # Get 'center' and 'radius' of the regions(s)
    region_center = []
    misr_max = []
    
    if refine_region:
        regions = get_regions_to_refine(capped_surface, region_points, path.join(dir_path, case_name))
        for i in range(len(regions) // 3):
            print("--- Region to refine ({}): {:.3f} {:.3f} {:.3f}"
                    .format(i + 1, regions[3 * i], regions[3 * i + 1], regions[3 * i + 2]))

        centerlineAnu, _, _ = compute_centerlines(source, regions, file_name_refine_region_centerlines, capped_surface,
                                                    resampling=0.1)

        # Extract the region centerline
        refine_region_centerline = []
        info = get_parameters(path.join(dir_path, case_name))
        num_anu = info["number_of_regions"]

        # Compute mean distance between points
        for i in range(num_anu):
            if not path.isfile(file_name_region_centerlines.format(i)):
                line = extract_single_line(centerlineAnu, i)
                locator = get_vtk_point_locator(centerlines)
                for j in range(line.GetNumberOfPoints() - 1, 0, -1):
                    point = line.GetPoints().GetPoint(j)
                    ID = locator.FindClosestPoint(point)
                    tmp_point = centerlines.GetPoints().GetPoint(ID)
                    dist = np.sqrt(np.sum((np.asarray(point) - np.asarray(tmp_point)) ** 2))
                    if dist <= tol:
                        break

                tmp = extract_single_line(line, 0, start_id=j)
                write_polydata(tmp, file_name_region_centerlines.format(i))

                # List of VtkPolyData sac(s) centerline
                refine_region_centerline.append(tmp)

            else:
                refine_region_centerline.append(read_polydata(file_name_region_centerlines.format(i)))

        # Merge the sac centerline
        region_centerlines = vtk_merge_polydata(refine_region_centerline)

        for region in refine_region_centerline:
            region_factor = 0.5
            region_center.append(region.GetPoints().GetPoint(int(region.GetNumberOfPoints() * region_factor)))
            tmp_misr = get_point_data_array(radiusArrayName, region)
            misr_max.append(tmp_misr.max())
    
    # Smooth surface
    if smoothing_method == "voronoi":
        print("--- Smooth surface: Voronoi smoothing\n")
        if not path.isfile(file_name_surface_smooth):
            # Get Voronoi diagram
            if not path.isfile(file_name_voronoi):
                voronoi = vmtk_compute_voronoi_diagram(surface, file_name_voronoi)
                write_polydata(voronoi, file_name_voronoi)
            else:
                voronoi = read_polydata(file_name_voronoi)

            # Get smooth Voronoi diagram
            if not path.isfile(file_name_voronoi_smooth):
                if refine_region:
                    smooth_voronoi = smooth_voronoi_diagram(voronoi, centerlines, smoothing_factor, region_centerlines)
                else:
                    smooth_voronoi = smooth_voronoi_diagram(voronoi, centerlines, smoothing_factor)

                write_polydata(smooth_voronoi, file_name_voronoi_smooth)
            else:
                smooth_voronoi = read_polydata(file_name_voronoi_smooth)

            # Envelope the smooth surface
            surface = create_new_surface(smooth_voronoi)

            # Uncapp the surface
            surface_uncapped = get_uncapped_surface(surface)

            # Check if there has been added new outlets
            num_outlets = centerlines.GetNumberOfLines()
            inlets, outlets = compute_centers(surface_uncapped)
            num_outlets_after = len(outlets) // 3

            if num_outlets != num_outlets_after:
                surface = vmtk_smooth_surface(surface, "laplace", iterations=200)
                write_polydata(surface, file_name_surface_smooth)
                print(("ERROR: Automatic clipping failed. You have to open {} and " +
                       "manually clipp the branch which still is capped. " +
                       "Overwrite the current {} and restart the script.").format(
                    file_name_surface_smooth, file_name_surface_smooth))
                sys.exit(0)

            surface = surface_uncapped

            # Smoothing to improve the quality of the elements
            # Consider to add a subdivision here as well.
            surface = vmtk_smooth_surface(surface, "laplace", iterations=200)

            # Write surface
            write_polydata(surface, file_name_surface_smooth)

        else:
            surface = read_polydata(file_name_surface_smooth)

    elif smoothing_method in ["laplace", "taubin"]:
        print("--- Smooth surface: {} smoothing\n".format(smoothing_method.capitalize()))
        if not path.isfile(file_name_surface_smooth):
            surface = vmtk_smooth_surface(surface, smoothing_method, iterations=400, passband=0.5)

            # Save the smoothed surface
            write_polydata(surface, file_name_surface_smooth)

        else:
            surface = read_polydata(file_name_surface_smooth)

    elif smoothing_method == "no_smooth" or None:
        print("--- No smoothing of surface\n")
    
    # Add flow extensions
    if create_flow_extensions:
        if not path.isfile(file_name_model_flow_ext):
            print("--- Adding flow extensions\n")
            # Add extension normal on boundary for atrium models
            extension = "boundarynormal"
            surface_extended = add_flow_extension(surface, centerlines, include_outlet=False,
                                                  extension_length=inlet_flow_extension_length,
                                                  extension_mode=extension)
            surface_extended = add_flow_extension(surface_extended, centerlines, include_outlet=True,
                                                  extension_length=outlet_flow_extension_length)

            surface_extended = vmtk_smooth_surface(surface_extended, "laplace", iterations=200)
            write_polydata(surface_extended, file_name_model_flow_ext)
        else:
            surface_extended = read_polydata(file_name_model_flow_ext)
    else:
        surface_extended = surface

    # Capp surface with flow extensions
    capped_surface = vmtk_cap_polydata(surface_extended)

    # Get new centerlines with the flow extensions
    if create_flow_extensions:
        if not path.isfile(file_name_flow_centerlines):
            print("--- Compute the model centerlines with flow extension.\n")
            # Compute the centerlines.
            inlet, outlets = get_centers_for_meshing(surface_extended, None, path.join(dir_path, case_name),
                                                     use_flow_extensions=True)
            # FIXME: There are several inlets and one outlet for atrium case
            source = inlet
            target = outlets
            centerlines, _, _ = compute_centerlines(source, target, file_name_flow_centerlines, capped_surface,
                                                    resampling=0.1)

        else:
            centerlines = read_polydata(file_name_flow_centerlines)

    if not path.isfile(file_name_seedX):
        print("\n--- Remeshing the surface based on a given seed point\n")
        remeshed_surface_seed = refine_mesh_seed(surface_extended, region_points, coarsening_factor, file_name_seedX)
    else:
        remeshed_surface_seed = read_polydata(file_name_seedX)

    # Compute mesh
    if not path.isfile(file_name_vtu_mesh):
        try:
            print("--- Computing mesh\n")
            mesh, remeshed_surface = generate_mesh_fsi(remeshed_surface_seed, Solid_thickness=0.25, TargetEdgeLength=0.23)
            assert remeshed_surface.GetNumberOfPoints() > 0, \
                "No points in surface mesh, try to remesh"
            assert mesh.GetNumberOfPoints() > 0, "No points in mesh, try to remesh"

        except:
            remeshed_surface_seed = mesh_alternative(remeshed_surface_seed)
            mesh, remeshed_surface = generate_mesh_fsi(remeshed_surface_seed, Solid_thickness=0.25, TargetEdgeLength=0.23)
            assert mesh.GetNumberOfPoints() > 0, "No points in mesh, after remeshing"
            assert remeshed_surface.GetNumberOfPoints() > 0, \
                "No points in surface mesh, try to remesh" 
        
        if scale_factor is not None:
            remeshed_surface = scale_surface(remeshed_surface, scale_factor)
            mesh = scale_mesh(mesh, scale_factor)

        write_mesh(compress_mesh, file_name_surface_name, file_name_vtu_mesh, file_name_xml_mesh,
                   mesh, remeshed_surface)

    else:
        mesh = read_polydata(file_name_vtu_mesh)

    network, probe_points = setup_model_network(centerlines, file_name_probe_points, region_center, verbose_print)

    # BSL method for mean inlet flow rate.
    parameters = get_parameters(path.join(dir_path, case_name))

    print("--- Computing flow rates and flow split, and setting boundary IDs\n")
    mean_inflow_rate = compute_flow_rate(None, inlet, parameters)

    find_boundaries(path.join(dir_path, case_name), mean_inflow_rate, network, mesh, verbose_print, None)

    # Display the flow split at the outlets, inlet flow rate, and probes.
    if viz:
        print("--- Visualizing flow split at outlets, inlet flow rate, and probes in VTK render window. ")
        print("--- Press 'q' inside the render window to exit.")
        visualize_model(network.elements, probe_points, surface_extended, mean_inflow_rate)

    print("--- Removing unused pre-processing files")
    files_to_remove = [file_name_centerlines, file_name_refine_region_centerlines, file_name_region_centerlines,
                       file_name_distance_to_sphere_diam, file_name_distance_to_sphere_const,
                       file_name_distance_to_sphere_curv, file_name_voronoi, file_name_voronoi_smooth,
                       file_name_surface_smooth, file_name_model_flow_ext, file_name_clipped_model,
                       file_name_flow_centerlines, file_name_surface_name]
    for file in files_to_remove:
        if path.exists(file):
            remove(file)

def read_command_line():
    """
    Read arguments from commandline and return all values in a dictionary.
    """
    parser = argparse.ArgumentParser(
        description="Automated pre-processing for vascular modeling.")

    parser.add_argument('-v', '--verbosity',
                        dest='verbosity',
                        type=str2bool,
                        default=False,
                        help="Activates the verbose mode.")

    parser.add_argument('-i', '--inputModel',
                        type=str,
                        required=False,
                        dest='fileNameModel',
                        default='example/surface.vtp',
                        help="Input file containing the 3D model.")

    parser.add_argument('-cM', '--compress-mesh',
                        type=str2bool,
                        required=False,
                        dest='compressMesh',
                        default=False,
                        help="Compress output mesh after generation.")

    parser.add_argument('-sM', '--smoothingMethod',
                        type=str,
                        required=False,
                        dest='smoothingMethod',
                        default="laplace",
                        choices=["voronoi", "no_smooth", "laplace", "taubin"],
                        help="Smoothing method, for now only Voronoi smoothing is available." +
                             " For Voronoi smoothing you can also control smoothingFactor" +
                             " (default = 0.25).")

    parser.add_argument('-c', '--coarseningFactor',
                        type=float,
                        required=False,
                        dest='coarseningFactor',
                        default=1.0,
                        help="Refine or coarsen the standard mesh size. The higher the value the coarser the mesh.")

    parser.add_argument('-sF', '--smoothingFactor',
                        type=float,
                        required=False,
                        dest='smoothingFactor',
                        default=0.25,
                        help="smoothingFactor for VoronoiSmoothing, removes all spheres which" +
                             " has a radius < MISR*(1-0.25), where MISR varying along the centerline.")

    parser.add_argument('-m', '--meshingMethod',
                        dest="meshingMethod",
                        type=str,
                        choices=["diameter", "curvature", "constant"],
                        default="curvature")

    parser.add_argument('-el', '--edge-length',
                        dest="edgeLength",
                        default=None,
                        type=float,
                        help="Characteristic edge length used for meshing.")

    parser.add_argument('-r', '--refine-region',
                        dest="refineRegion",
                        type=str2bool,
                        default=False,
                        help="Determine weather or not to refine a specific region of " +
                             "the input model. Default is False.")

    parser.add_argument('-rp', '--region-points',
                        dest="regionPoints",
                        type=float,
                        nargs="+",
                        default=None,
                        help="If -r or --refine-region is True, the user can provide the point(s)"
                             " which defines the regions to refine. " +
                             "Example providing the points (0.1, 5.0, -1) and (1, -5.2, 3.21):" +
                             " --region-points 0.1 5 -1 1 5.24 3.21")

    parser.add_argument('-f', '--flowext',
                        dest="flowExtension",
                        default=False,
                        type=str2bool,
                        help="Add flow extensions to to the model.")

    parser.add_argument('-fli', '--inletFlowext',
                        dest="inletFlowExtLen",
                        default=0,
                        type=float,
                        help="Length of flow extensions at inlet(s).")

    parser.add_argument('-flo', '--outletFlowext',
                        dest="outletFlowExtLen",
                        default=0,
                        type=float,
                        help="Length of flow extensions at outlet(s).")

    parser.add_argument('-vz', '--visualize',
                        dest="viz",
                        default=True,
                        type=str2bool,
                        help="Visualize surface, inlet, outlet and probes after meshing.")

    parser.add_argument('-sc', '--scale-factor',
                    default=0.001,
                    type=float,
                    help="Scale input model by this factor.")



    args, _ = parser.parse_known_args()

    if args.verbosity:
        print()
        print("--- VERBOSE MODE ACTIVATED ---")

        def verbose_print(*args):
            for arg in args:
                print(arg, end=' ')
                print()
    else:
        verbose_print = lambda *a: None

    verbose_print(args)

    return dict(filename_model=args.fileNameModel, verbose_print=verbose_print, smoothing_method=args.smoothingMethod,
                smoothing_factor=args.smoothingFactor, meshing_method=args.meshingMethod,
                refine_region=args.refineRegion, create_flow_extensions=args.flowExtension, viz=args.viz,
                coarsening_factor=args.coarseningFactor, inlet_flow_extension_length=args.inletFlowExtLen,
                edge_length=args.edgeLength, region_points=args.regionPoints, compress_mesh=args.compressMesh,
                outlet_flow_extension_length=args.outletFlowExtLen, scale_factor=args.scale_factor)

if __name__ == "__main__":
    run_pre_processing(**read_command_line())