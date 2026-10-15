package holylois.residency;
import holylois.residency.mixin.*;

import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.item.*;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.entity.Visibility;
import java.nio.file.*;
import java.util.*;

/** Generated fixtures only. Kept out of the production candidate jar. */
public final class NativeResidencyTest implements ModInitializer {
    private static final ChunkPos FAR=new ChunkPos(10000,10000);
    private static final UUID COW=UUID.fromString("00000000-0000-0000-0000-000000002131");
    private static final UUID ARMOR=UUID.fromString("00000000-0000-0000-0000-000000002132");
    private static final UUID LOCAL=UUID.fromString("00000000-0000-0000-0000-000000002133");
    private int ticks,phase;private long reloadTick;
    private static void check(boolean value,String text){if(!value)throw new IllegalStateException(text);}
    @Override public void onInitialize() {
        if(!Boolean.getBoolean("holylois.residency.test"))throw new IllegalStateException("Fixture flag required");
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            check(server.getPort()==25566,"Fixture requires private port");
            var level=server.overworld();level.setChunkForced(0,0,true);level.getChunk(0,0);
            ((LevelAccess)(Object)level).residency$manager().updateChunkStatus(FAR,Visibility.TRACKED);
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            try {
                ticks++;var level=server.overworld();var manager=((LevelAccess)(Object)level).residency$manager();
                if(phase==0&&ticks>30&&manager.areEntitiesLoaded(FAR.pack())) {
                    check(ResidencyGuard.orphan(level,FAR.pack()),"Fixture must have no terrain holder");
                    var cow=EntityTypes.COW.create(level,EntitySpawnReason.COMMAND);
                    cow.setUUID(COW);cow.setPos(160001,70,160001);cow.setPersistenceRequired();cow.setCustomName(Component.literal("Residency cow fixture"));
                    check(level.addFreshEntity(cow),"Cow add failed");
                    var armor=EntityTypes.ARMOR_STAND.create(level,EntitySpawnReason.COMMAND);
                    armor.setUUID(ARMOR);armor.setPos(160003,70,160003);
                    armor.setItemSlot(EquipmentSlot.HEAD,new ItemStack(Items.DIAMOND_HELMET));
                    check(level.addFreshEntity(armor),"Armor add failed");
                    var local=EntityTypes.COW.create(level,EntitySpawnReason.COMMAND);
                    local.setUUID(LOCAL);local.setPos(1,70,1);local.setPersistenceRequired();local.setNoAi(true);
                    check(level.addFreshEntity(local),"Local add failed");phase=1;
                }
                if(phase==1&&ticks>600) {
                    check(!manager.isLoaded(COW)&&!manager.isLoaded(ARMOR),"Orphan entities did not unload");
                    check(manager.isLoaded(LOCAL),"Resident entity was unloaded");
                    check(ResidencyGuard.orphan(level,FAR.pack()),"Repair unexpectedly loaded terrain");
                    manager.updateChunkStatus(FAR,Visibility.TRACKED);reloadTick=ticks;phase=2;
                }
                if(phase==2&&ticks>reloadTick+5&&manager.isLoaded(COW)&&manager.isLoaded(ARMOR)) {
                    var cow=manager.getEntityGetter().get(COW);var armor=manager.getEntityGetter().get(ARMOR);
                    check(cow!=null&&"Residency cow fixture".equals(cow.getName().getString()),"Cow identity/name was not preserved");
                    check(armor instanceof ArmorStand&&((ArmorStand)armor).getItemBySlot(EquipmentSlot.HEAD).is(Items.DIAMOND_HELMET),"Equipment was not preserved");
                    check(manager.isLoaded(LOCAL),"Loaded resident lost after reload");
                    // A pending terrain unload must block reconciliation until the native queue completes.
                    var chunks=level.getChunkSource().chunkMap;var access=(ChunkAccess)(Object)chunks;
                    var holder=chunks.getUpdatingChunkIfPresent(ChunkPos.ZERO.pack());check(holder!=null,"Resident holder missing");
                    access.residency$pending().put(FAR.pack(),holder);
                    try {check(!ResidencyGuard.orphan(level,FAR.pack()),"Pending unload was treated as orphan");}
                    finally {access.residency$pending().remove(FAR.pack());}
                    Files.writeString(Path.of("residency-test-receipt.json"),"{\"passed\":true,\"orphan_unloaded\":true,\"resident_preserved\":true,\"same_uuid_reloaded\":true,\"name_preserved\":true,\"equipment_preserved\":true,\"pending_unload_protected\":true,\"terrain_not_loaded\":true}\n",StandardOpenOption.CREATE_NEW);
                    System.out.println("RESIDENCY_NATIVE_TEST_PASS");phase=3;server.halt(false);
                }
                if(ticks>1400&&phase!=3)throw new IllegalStateException("Residency fixture timeout phase="+phase);
            }catch(Exception error) {
                System.err.println("RESIDENCY_NATIVE_TEST_FAIL "+error.getClass().getSimpleName()+": "+error.getMessage());
                phase=3;server.halt(false);
            }
        });
    }
}
