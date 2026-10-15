package holylois.residency;
import holylois.residency.mixin.*;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.world.level.entity.Visibility;
import java.nio.file.*;

/** Controlled Chunky generation probe; no production guard or live world. */
public final class NativeUnloadProbe implements ModInitializer {
    private int ticks,phase;private int observedPeak;
    private void command(net.minecraft.server.MinecraftServer server,String text) {
        server.getCommands().performPrefixedCommand(server.createCommandSourceStack(),text);
    }
    @Override public void onInitialize() {
        if(!Boolean.getBoolean("holylois.unload.probe"))throw new IllegalStateException("Private probe flag missing");
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            if(server.getPort()!=25566)throw new IllegalStateException("Probe requires private port");
            command(server,"chunky world minecraft:overworld");command(server,"chunky center 5000 5000");
            command(server,"chunky radius 160");command(server,"chunky shape square");command(server,"chunky pattern region");command(server,"chunky start");
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            try {
                ticks++;var level=server.overworld();var manager=((LevelAccess)(Object)level).residency$manager();
                var visibility=((ManagerAccess)(Object)manager).residency$visibility();observedPeak=Math.max(observedPeak,visibility.size());
                if(ticks<2400||phase!=0)return;
                command(server,"chunky pause minecraft:overworld");phase=1;
                int orphan=0,totalTracked=0;
                var chunks=level.getChunkSource().chunkMap;var access=(ChunkAccess)(Object)chunks;
                for(var entry:visibility.long2ObjectEntrySet()) {
                    if(entry.getValue()!=Visibility.TRACKED)continue;totalTracked++;long key=entry.getLongKey();
                    if(chunks.getUpdatingChunkIfPresent(key)==null&&access.residency$visible(key)==null&&!access.residency$pending().containsKey(key))orphan++;
                }
                Files.writeString(Path.of("unload-probe-receipt.json"),"{\"peak_entity_chunk_records\":"+observedPeak+",\"tracked_chunks\":"+totalTracked+",\"orphan_tracked_chunks\":"+orphan+",\"ticks\":"+ticks+"}\n",StandardOpenOption.CREATE_NEW);
                System.out.println("UNLOAD_PROBE_PASS");server.halt(false);
            }catch(Exception error){System.err.println("UNLOAD_PROBE_FAIL "+error.getClass().getSimpleName()+": "+error.getMessage());phase=1;server.halt(false);}
        });
    }
}
