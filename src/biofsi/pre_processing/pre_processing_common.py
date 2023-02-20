from vmtkmeshgeneratorfsi import vmtkMeshGeneratorFsi
import numpy as np
import vtk
from vmtk import vmtkscripts
from morphman import write_polydata

def scale_surface(surface, scale_factor):
    """
    Scale the input surface by a factor scale_factor.
    Args:
        surface (vtkPolyData): Input surface to be scaled
        scale_factor (float): Scaling factor
    Returns:
        scaled_surface (vtkPolyData): Scaled input surface
    """
    surface_scaler = vmtkscripts.vmtkSurfaceScaling()
    surface_scaler.Surface = surface
    surface_scaler.ScaleFactor = scale_factor
    surface_scaler.Execute()

    # Get scaled surface
    scaled_surface = surface_scaler.Surface

    return scaled_surface

def scale_mesh(mesh, scale_factor):
    """
    Scale the input mesh by a factor scale_factor.
    Args:
        mesh (vtkUnstructuredGrid): Input mesh to be scaled
        scale_factor (float): Scaling factor
    Returns:
        scaled_mesh (vtkUnstructuredGrid): Scaled input mesh
    """
    mesh_scaler = vmtkscripts.vmtkMeshScaling()
    mesh_scaler.Mesh = mesh
    mesh_scaler.ScaleFactor = scale_factor
    mesh_scaler.Execute()

    # Get scaled mesh
    scaled_mesh = mesh_scaler.Mesh

    return scaled_mesh

def refine_mesh_seed(surface, seedX, coarsening_factor, seedXFile):
    """
    Refine mesh based on a seed point.
    Args:
        surface (vtkPolyData): Surface model to be meshed.
        seedX (list): Coordinates of the seed point.
        seedXFile (str): Path to the output file.
    Returns:
        surface (vtkPolyData): Surface model
    """
    # Parameters
    TargetEdgeLength_s = 0.25
    factor_scale = coarsening_factor  # multiplier for max element size
    factor_shape = 0.3  # 1==linear scale based on distance

    N = surface.GetNumberOfPoints()
    dist_array = np.zeros(N)
    # Compute distance
    for i in range(N):
        piX = surface.GetPoints().GetPoint(i)
        dist_array[i] = np.sqrt(np.sum((np.asarray(seedX) - np.asarray(piX))**2))
    dist_array[:] = dist_array[:] - dist_array.min()  # between 0 and max
    dist_array[:] = dist_array[:] / dist_array.max() + 1  # between 1 and 2
    dist_array[:] = dist_array[:]**factor_shape - 1  # between 0 and 2^factor_shape
    dist_array[:] = dist_array[:] / dist_array.max()  # between 0 and 1
    dist_array[:] = dist_array[:]*(factor_scale-1) + 1  # between 1 and factor_scale
    dist_array[:] = dist_array[:] * TargetEdgeLength_s  # Scaled TargetEdgeLength
    array = vtk.vtkDoubleArray()
    array.SetNumberOfComponents(1)
    array.SetNumberOfTuples(N)
    array.SetName("Size")
    for i in range(N):
        array.SetTuple1(i, dist_array[i])
    surface.GetPointData().AddArray(array)

    remeshing = vmtkscripts.vmtkSurfaceRemeshing()
    remeshing.Surface = surface
    remeshing.TargetEdgeLength = TargetEdgeLength_s
    remeshing.MaxEdgeLength = factor_scale*remeshing.TargetEdgeLength
    remeshing.MinEdgeLength = 0.5*remeshing.TargetEdgeLength
    remeshing.TargetEdgeLengthArrayName = "Size"
    remeshing.ElementSizeMode = "edgelengtharray"
    remeshing.Execute()
    surface = remeshing.Surface

    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(seedXFile)
    writer.SetInputData(surface)
    writer.Update()
    writer.Write()
    
    return surface

def generate_mesh_fsi(surface, Solid_thickness, TargetEdgeLength):
    """
    Generates a mesh suitable for FSI from a input surface model.
    Args:
        surface (vtkPolyData): Surface model to be meshed.
    Returns:
        mesh (vtkUnstructuredGrid): Output mesh
        remeshedsurface (vtkPolyData): Remeshed version of the input model
    """

    # Parameters
    meshGenerator = vmtkMeshGeneratorFsi()
    meshGenerator.Surface = surface
    meshGenerator.ElementSizeMode = 'edgelength'
    meshGenerator.TargetEdgeLength = TargetEdgeLength
    meshGenerator.MaxEdgeLength = 15*meshGenerator.TargetEdgeLength
    meshGenerator.MinEdgeLength = 5*meshGenerator.TargetEdgeLength
    meshGenerator.BoundaryLayer = 1
    meshGenerator.NumberOfSubLayers = 2
    meshGenerator.BoundaryLayerOnCaps = 0
    meshGenerator.BoundaryLayerThicknessFactor = Solid_thickness / TargetEdgeLength 
    meshGenerator.SubLayerRatio = 1
    meshGenerator.Tetrahedralize = 1
    meshGenerator.VolumeElementScaleFactor = 0.8
    meshGenerator.EndcapsEdgeLengthFactor = 1.0

    # Cells and walls numbering
    meshGenerator.SolidSideWallId = 11
    meshGenerator.InterfaceId_fsi = 22
    meshGenerator.InterfaceId_outer = 33
    meshGenerator.VolumeId_fluid = 0  # (keep to 0)
    meshGenerator.VolumeId_solid = 1

    meshGenerator.Execute()

    # Remeshed surface, store for later
    remeshSurface = meshGenerator.RemeshedSurface

    # Full mesh
    mesh = meshGenerator.Mesh

    return mesh, remeshSurface

def write_mesh(compress_mesh, file_name_surface_name, file_name_vtu_mesh, file_name_xml_mesh, mesh, remeshed_surface):
    """
    Writes the mesh to DOLFIN format, and compresses to .gz format

    Args:
        compress_mesh (bool): Compressed mesh to zipped format
        file_name_surface_name (str): Path to remeshed surface model
        file_name_vtu_mesh (str): Path to VTK mesh
        file_name_xml_mesh (str): Path to XML mesh
        mesh (vtuUnstructuredGrid): Meshed surface model
        remeshed_surface (vtkPolyData): Remeshed surface model
    """
    # Write mesh in VTU format
    write_polydata(remeshed_surface, file_name_surface_name)
    write_polydata(mesh, file_name_vtu_mesh)

    # Write mesh to FEniCS to format
    meshWriter = vmtkscripts.vmtkMeshWriter()
    meshWriter.CellEntityIdsArrayName = "CellEntityIds"
    meshWriter.Mesh = mesh
    meshWriter.Mode = "ascii"
    meshWriter.Compressed = compress_mesh
    meshWriter.WriteRegionMarkers = 1
    meshWriter.OutputFileName = file_name_xml_mesh
    meshWriter.Execute()
