FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml ./
COPY src ./src
RUN mvn --batch-mode package

FROM itzg/minecraft-server:java21 AS paper-runtime
WORKDIR /opt/paper-runtime
# 固定发行包及校验值；联网下载和原版补丁处理都在构建阶段完成。
ADD --checksum=sha256:35e2dfa66b3491b9d2f0bb033679fa5aca1e1fdf097e7a06a80ce8afeda5c214 https://fill-data.papermc.io/v1/objects/35e2dfa66b3491b9d2f0bb033679fa5aca1e1fdf097e7a06a80ce8afeda5c214/paper-1.21.6-48.jar ./paper-1.21.6-48.jar
RUN java -Dpaperclip.patchonly=true -jar paper-1.21.6-48.jar
RUN chmod -R a+rX /opt/paper-runtime

FROM itzg/minecraft-server:java21
COPY --from=paper-runtime /opt/paper-runtime /opt/paper-runtime
# 固定支持 MC 1.21.6 的 WorldEdit；启动脚本把 /plugins 同步到 /data/plugins。
COPY --from=build /build/target/semantic-regions.jar /plugins/SemanticRegions.jar
ADD --checksum=sha256:1107500d57b7a921ce984090033afcc2a272b1ed6a0336a9fd7f31f7acb63f0f https://cdn.modrinth.com/data/1u6JkXh5/versions/Jk1z2u7n/worldedit-bukkit-7.3.16.jar /plugins/WorldEdit.jar
ADD --checksum=sha256:707255ab71069cda98dd1217ed1f16f88f3e40505e16416794f32d0e2666ebd3 https://cdn.modrinth.com/data/DKY9btbd/versions/PO4MKx7e/worldguard-bukkit-7.0.14-dist.jar /plugins/WorldGuard.jar
RUN chmod 644 /plugins/*.jar
COPY start.sh /semantic-start.sh
ENTRYPOINT ["sh", "/semantic-start.sh"]
