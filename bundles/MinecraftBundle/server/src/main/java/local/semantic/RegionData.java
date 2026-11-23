package local.semantic;

import java.util.List;

/** Coordinates are absolute block coordinates; bounds include both endpoints. */
public record RegionData(
        int schemaVersion, String id, String name, String type, String description,
        String world, String worldUuid, String dimension, Geometry geometry,
        Entrance entrance, String createdBy, String createdAt, String updatedAt) {
    public record Point(int x, int y, int z) {}
    public record Point2(int x, int z) {}
    public record Geometry(String shape, Point min, Point max, List<Point2> points) {}
    public record Entrance(Point position, float yaw) {}

    public RegionData withMetadata(String name, String type, String description, Entrance entrance,
                                   Geometry geometry, String now) {
        return new RegionData(schemaVersion, id, name, type, description, world, worldUuid,
                dimension, geometry, entrance, createdBy, createdAt, now);
    }
}
