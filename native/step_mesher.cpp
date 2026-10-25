// Copyright (C) 2026 David-Seco-Retuerto. SPDX-License-Identifier: AGPL-3.0-only
// STEP parsing runs in a separate process. OCCT retains its own LGPL terms.
#include <BRep_Tool.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <BRepPrimAPI_MakeBox.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <Poly_Triangulation.hxx>
#include <STEPControl_Reader.hxx>
#include <STEPControl_Writer.hxx>
#include <Standard_Failure.hxx>
#include <Standard_Version.hxx>
#include <TopAbs_Orientation.hxx>
#include <TopExp_Explorer.hxx>
#include <TopLoc_Location.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <array>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using Vertex = std::array<double, 3>;
using Triangle = std::array<int, 3>;

void meshStep(const std::string& input, const std::string& output) {
    STEPControl_Reader reader;
    if (reader.ReadFile(input.c_str()) != IFSelect_RetDone)
        throw std::runtime_error("OpenCascade could not read this STEP file.");
    if (!reader.TransferRoots())
        throw std::runtime_error("The STEP file contains no transferable shapes.");
    TopoDS_Shape shape = reader.OneShape();
    if (shape.IsNull()) throw std::runtime_error("The STEP file contains no shape.");
    BRepMesh_IncrementalMesh(shape, .08, false, .35, true).Perform();
    std::vector<Vertex> vertices;
    std::vector<Triangle> triangles;
    for (TopExp_Explorer faces(shape, TopAbs_FACE); faces.More(); faces.Next()) {
        TopoDS_Face face = TopoDS::Face(faces.Current());
        TopLoc_Location location;
        Handle(Poly_Triangulation) mesh = BRep_Tool::Triangulation(face, location);
        if (mesh.IsNull()) continue;
        if (vertices.size() + mesh->NbNodes() > 150000 || triangles.size() + mesh->NbTriangles() > 60000)
            throw std::runtime_error("This model is too detailed for the lightweight preview. Open it in a full CAD viewer.");
        int offset = static_cast<int>(vertices.size());
        for (int i = 1; i <= mesh->NbNodes(); ++i) {
            gp_Pnt p = mesh->Node(i).Transformed(location.Transformation());
            Vertex v{p.X(), p.Y(), p.Z()};
            for (double value : v)
                if (!std::isfinite(value)) throw std::runtime_error("The STEP mesh contains invalid coordinates.");
            vertices.push_back(v);
        }
        for (int i = 1; i <= mesh->NbTriangles(); ++i) {
            int a, b, c;
            mesh->Triangle(i).Get(a, b, c);
            if (face.Orientation() == TopAbs_REVERSED) std::swap(a, c);
            triangles.push_back({offset + a - 1, offset + b - 1, offset + c - 1});
        }
    }
    if (triangles.empty()) throw std::runtime_error("No renderable surfaces were found in this STEP file.");
    Vertex low = vertices.front(), high = vertices.front(), size{}, center{};
    for (const auto& v : vertices)
        for (int i = 0; i < 3; ++i) { low[i] = std::min(low[i], v[i]); high[i] = std::max(high[i], v[i]); }
    for (int i = 0; i < 3; ++i) { size[i] = high[i] - low[i]; center[i] = (low[i] + high[i]) / 2; }
    double radius = 0;
    for (const auto& v : vertices) {
        double squared = 0;
        for (int i = 0; i < 3; ++i) squared += (v[i] - center[i]) * (v[i] - center[i]);
        radius = std::max(radius, std::sqrt(squared));
    }
    if (radius == 0) radius = 1;
    std::ofstream file(std::filesystem::u8path(output), std::ios::binary | std::ios::trunc);
    if (!file) throw std::runtime_error("Cannot create the preview mesh output.");
    file << std::setprecision(17) << "{\"vertices\":[";
    for (size_t n = 0; n < vertices.size(); ++n) {
        if (n) file << ',';
        file << '[';
        for (int i = 0; i < 3; ++i) { if (i) file << ','; file << (vertices[n][i] - center[i]) / radius; }
        file << ']';
    }
    file << "],\"triangles\":[";
    for (size_t n = 0; n < triangles.size(); ++n) {
        if (n) file << ',';
        file << '[' << triangles[n][0] << ',' << triangles[n][1] << ',' << triangles[n][2] << ']';
    }
    file << "],\"size_mm\":[" << size[0] << ',' << size[1] << ',' << size[2] << "]}";
    file.close();
    if (!file) throw std::runtime_error("Cannot finish writing the preview mesh.");
}

int run(const std::vector<std::string>& args) {
    try {
        if (args.size() == 1 && args[0] == "--self-test") {
            std::cout << "{\"native_reader\":\"OCCT\",\"version\":\"" << OCC_VERSION_COMPLETE << "\"}\n";
            return 0;
        }
        if (args.size() == 2 && args[0] == "--make-test-step") {
            STEPControl_Writer writer;
            if (writer.Transfer(BRepPrimAPI_MakeBox(2, 4, 6).Shape(), STEPControl_AsIs) != IFSelect_RetDone ||
                writer.Write(args[1].c_str()) != IFSelect_RetDone)
                throw std::runtime_error("Cannot write the synthetic STEP fixture.");
            return 0;
        }
        if (args.size() != 3 || args[0] != "--mesh") {
            std::cerr << "Usage: kicad-step-mesher --mesh INPUT.step OUTPUT.json\n";
            return 2;
        }
        meshStep(args[1], args[2]);
        return 0;
    } catch (const Standard_Failure& error) {
        std::cerr << "OpenCascade: " << (error.GetMessageString() ? error.GetMessageString() : "STEP reader failure") << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
    }
    return 1;
}

#ifdef _WIN32
std::string utf8(const wchar_t* text) {
    return std::filesystem::path(text).u8string();
}

int wmain(int argc, wchar_t** argv) {
    std::vector<std::string> args;
    try { for (int i = 1; i < argc; ++i) args.push_back(utf8(argv[i])); }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
    return run(args);
}
#else
int main(int argc, char** argv) { return run(std::vector<std::string>(argv + 1, argv + argc)); }
#endif
