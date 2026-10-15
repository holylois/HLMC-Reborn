package holylois.residency;
import holylois.residency.mixin.*;

import it.unimi.dsi.fastutil.longs.Long2LongOpenHashMap;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.entity.Visibility;
import org.slf4j.LoggerFactory;
import java.util.IdentityHashMap;

/** Reconcile visible entity sections whose terrain holders have already disappeared. */
public final class ResidencyGuard implements ModInitializer {
    static final int GRACE_TICKS=200, SCAN_BUDGET=64, REPAIR_BUDGET=4;
    private static final IdentityHashMap<ServerLevel,State> STATES=new IdentityHashMap<>();
    private static final class State {
        final Long2LongOpenHashMap since=new Long2LongOpenHashMap();
        long[] snapshot=new long[0]; int index; long nextSnapshot; long repairs; boolean disabled;
        State(){since.defaultReturnValue(-1);}
    }
    @Override public void onInitialize() {
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            for(var level:server.getAllLevels())reconcile(level,server.getTickCount());
        });
        ServerLifecycleEvents.SERVER_STOPPED.register(server -> STATES.clear());
    }
    static boolean orphan(ServerLevel level,long key) {
        var chunks=level.getChunkSource().chunkMap;
        var access=(ChunkAccess)(Object)chunks;
        return chunks.getUpdatingChunkIfPresent(key)==null
            && access.residency$visible(key)==null
            && !access.residency$pending().containsKey(key);
    }
    static void reconcile(ServerLevel level,long tick) {
        var state=STATES.computeIfAbsent(level,k -> new State());
        if(state.disabled)return;
        var manager=((LevelAccess)(Object)level).residency$manager();
        var visible=((ManagerAccess)(Object)manager).residency$visibility();
        if(state.index>=state.snapshot.length) {
            if(tick<state.nextSnapshot)return;
            if(visible.size()>200_000) {
                state.disabled=true;
                LoggerFactory.getLogger("HolyLoisResidency").error("Entity residency inventory exceeds reviewed budget; reconciliation disabled for this dimension");
                return;
            }
            state.snapshot=visible.keySet().toLongArray();state.index=0;state.nextSnapshot=tick+GRACE_TICKS;
            state.since.keySet().retainAll(visible.keySet());
        }
        int scanned=0,repaired=0;long deadline=System.nanoTime()+1_000_000L;
        while(state.index<state.snapshot.length&&scanned++<SCAN_BUDGET&&repaired<REPAIR_BUDGET) {
            if(System.nanoTime()>deadline)break;
            long key=state.snapshot[state.index++];
            if(visible.get(key)!=Visibility.TRACKED||!orphan(level,key)) {state.since.remove(key);continue;}
            long first=state.since.get(key);
            if(first<0) {state.since.put(key,tick);continue;}
            if(tick-first<GRACE_TICKS)continue;
            // Native callbacks stop tracking; the native manager saves and unloads on its normal tick.
            manager.updateChunkStatus(ChunkPos.unpack(key),Visibility.HIDDEN);
            state.since.remove(key);state.repairs++;repaired++;
        }
        if(repaired>0&&state.repairs%100<repaired)
            LoggerFactory.getLogger("HolyLoisResidency").info("Reconciled {} orphaned entity sections through native unloading",state.repairs);
    }
}
