package holylois.residency;

import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponentMap;
import net.minecraft.core.component.TypedDataComponent;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffect;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import java.util.WeakHashMap;

/**
 * Runeforged recomputes every player's weapon/armor attribute modifiers each tick (about 8 ms per player).
 * Its inputs are the held weapon, the four armor slots and active effects (Slowness compensation, max-health cap),
 * so skip the recompute while those are unchanged and refresh at least once a second. Server thread only.
 */
public final class AttributeThrottle {
    static final int REFRESH_TICKS=20;
    private static final EquipmentSlot[] ARMOR={EquipmentSlot.HEAD,EquipmentSlot.CHEST,EquipmentSlot.LEGS,EquipmentSlot.FEET};
    private static final WeakHashMap<ServerPlayer,State> STATES=new WeakHashMap<>();
    public static boolean enabled=true;
    public static long full,skipped;
    private static final class State {
        final ItemStack[] gear=new ItemStack[5]; int effects, tick; boolean applying, dirty=true;
    }
    private AttributeThrottle() {}

    /** True when the recompute can be skipped; otherwise records the inputs this recompute uses. */
    public static boolean skip(ServerPlayer player) {
        State state=STATES.computeIfAbsent(player,key -> new State());
        int effects=effects(player), age=player.tickCount-state.tick;
        if(enabled&&!state.dirty&&!state.applying&&age>=0&&age<REFRESH_TICKS&&effects==state.effects&&same(player,state)) {
            skipped++;return true;
        }
        state.gear[0]=player.getWeaponItem().copy();
        for(int i=0;i<4;i++)state.gear[i+1]=player.getItemBySlot(ARMOR[i]).copy();
        state.effects=effects;state.tick=player.tickCount;state.applying=true;state.dirty=false;full++;
        return false;
    }
    public static void applied(ServerPlayer player) {
        State state=STATES.get(player);
        if(state!=null)state.applying=false;
    }
    /** A weapon applied outside the regular recompute (off-hand attacks) must be undone by the next one. */
    public static void weaponApplied(ServerPlayer player) {
        State state=STATES.get(player);
        if(state!=null&&!state.applying)state.dirty=true;
    }
    public static void forget(ServerPlayer player) { STATES.remove(player); }
    private static boolean same(ServerPlayer player,State state) {
        if(!same(state.gear[0],player.getWeaponItem()))return false;
        for(int i=0;i<4;i++)if(!same(state.gear[i+1],player.getItemBySlot(ARMOR[i])))return false;
        return true;
    }
    /** Component values are immutable and a copy shares them, so identity spots every set/remove without deep equals. */
    public static boolean same(ItemStack stored,ItemStack current) {
        if(stored.getItem()!=current.getItem()||stored.getCount()!=current.getCount())return false;
        return contains(stored.getComponents(),current.getComponents())&&contains(current.getComponents(),stored.getComponents());
    }
    private static boolean contains(DataComponentMap map,DataComponentMap other) {
        for(TypedDataComponent<?> component:other)if(map.get(component.type())!=component.value())return false;
        return true;
    }
    private static int effects(ServerPlayer player) {
        int hash=player.getActiveEffects().size();
        for(var effect:player.getActiveEffects()) {
            Holder<MobEffect> type=effect.getEffect();
            hash+=type.hashCode()*31+effect.getAmplifier()+1;
        }
        return hash;
    }
}
