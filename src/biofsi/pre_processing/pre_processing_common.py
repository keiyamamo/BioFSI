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
