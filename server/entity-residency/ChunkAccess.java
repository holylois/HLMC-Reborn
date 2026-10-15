package holylois.residency.mixin;
import it.unimi.dsi.fastutil.longs.Long2ObjectLinkedOpenHashMap;
import net.minecraft.server.level.ChunkMap;
import net.minecraft.server.level.ChunkHolder;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;
@Mixin(ChunkMap.class)
public interface ChunkAccess {
    @Invoker("getVisibleChunkIfPresent") ChunkHolder residency$visible(long key);
    @Accessor("pendingUnloads") Long2ObjectLinkedOpenHashMap<ChunkHolder> residency$pending();
}
