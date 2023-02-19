from vmtkmeshgeneratorfsi import vmtkMeshGeneratorFsi

def generate_mesh_fsi(surface):
    """
    Generates a mesh suitable for FSI from a input surface model.
    Args:
        surface (vtkPolyData): Surface model to be meshed.
    Returns:
        mesh (vtkUnstructuredGrid): Output mesh
        remeshedsurface (vtkPolyData): Remeshed version of the input model
    """

    from vmtkmeshgeneratorfsi import vmtkMeshGeneratorFsi

    # Parameters
    #TODO: It should be possible to change parameters from commmad line
    #FIXEM: low TargetEdgeLength results in an error
    TargetEdgeLength = 0.38
    Solid_thickness = 0.25
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