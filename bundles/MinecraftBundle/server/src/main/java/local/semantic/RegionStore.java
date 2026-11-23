package local.semantic;

import com.google.gson.FieldNamingPolicy;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;
import java.util.regex.Pattern;

/** One JSON per region is both the source of truth and the exported artifact. */
public final class RegionStore {
    private static final Pattern ID = Pattern.compile("[a-z0-9][a-z0-9_-]{0,63}");
    private static final Gson JSON = new GsonBuilder().setPrettyPrinting().serializeNulls()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES).create();
    private final Path directory;

    public RegionStore(Path directory) throws IOException {
        this.directory = directory;
        Files.createDirectories(directory);
    }

    private Path file(String id) {
        if (!ID.matcher(id).matches())
            throw new IllegalArgumentException("ID 须为 1–64 位小写英文、数字、下划线或连字符，首位为英文或数字。");
        return directory.resolve(id + ".json");
    }

    public boolean exists(String id) { return Files.exists(file(id)); }

    public RegionData read(String id) throws IOException {
        Path path = file(id);
        if (!Files.exists(path)) throw new IllegalArgumentException("区域不存在：" + id);
        try {
            RegionData data = JSON.fromJson(Files.readString(path), RegionData.class);
            if (data == null || data.schemaVersion() != 1 || !id.equals(data.id())
                    || data.geometry() == null || data.worldUuid() == null)
                throw new IllegalArgumentException("Invalid region schema");
            return data;
        } catch (RuntimeException ex) {
            throw new IOException("区域 JSON 无效：" + id, ex);
        }
    }

    public void write(RegionData data) throws IOException {
        Path destination = file(data.id());
        Path temporary = Files.createTempFile(directory, ".region-", ".tmp");
        try {
            Files.writeString(temporary, JSON.toJson(data) + "\n", StandardCharsets.UTF_8);
            // 同目录原子替换：读取方不会看到只写了一半的 JSON。
            Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    public void delete(String id) throws IOException {
        if (!Files.deleteIfExists(file(id))) throw new IllegalArgumentException("区域不存在：" + id);
    }

    public List<String> list() throws IOException {
        try (var files = Files.list(directory)) {
            return files.map(p -> p.getFileName().toString())
                    .filter(n -> n.endsWith(".json"))
                    .map(n -> n.substring(0, n.length() - 5))
                    .filter(n -> ID.matcher(n).matches()).sorted().toList();
        }
    }
}
