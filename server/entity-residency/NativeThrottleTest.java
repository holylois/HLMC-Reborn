package holylois.residency;

import com.ultimatearpg.combat.ArpgPlayerAttributeService;
import com.ultimatearpg.item.*;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.entity.FakePlayer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.core.Holder;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.ai.attributes.Attribute;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import java.nio.file.*;
import java.util.*;

/** Generated fixture only. Kept out of the production candidate jar. */
public final class NativeThrottleTest implements ModInitializer {
    private static final List<Holder<Attribute>> WATCHED=List.of(Attributes.MAX_HEALTH,Attributes.ARMOR,Attributes.ARMOR_TOUGHNESS,
        Attributes.KNOCKBACK_RESISTANCE,Attributes.MOVEMENT_SPEED,Attributes.ATTACK_SPEED,Attributes.ATTACK_KNOCKBACK,Attributes.ENTITY_INTERACTION_RANGE);
    private int ticks;
    private static void check(boolean value,String text){if(!value)throw new IllegalStateException(text);}
    @Override public void onInitialize() {
        if(!Boolean.getBoolean("holylois.throttle.test"))throw new IllegalStateException("Fixture flag required");
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            if(++ticks!=40)return;
            try { run(server); }
            catch(Throwable error) { System.out.println("THROTTLE_NATIVE_TEST_FAIL "+error); error.printStackTrace(System.out); }
            server.halt(false);
        });
    }
    /** Real Runeforged gear: affixes that drive every attribute the recompute writes. */
    private static ItemStack rolled(Item item,MinecraftServer server) {
        ItemStack stack=new ItemStack(item);
        float roll=0.4f+server.overworld().getRandom().nextFloat()*0.6f;
        List<ArpgAffixInstance> affixes=new ArrayList<>();
        for(String id:ArpgWeaponHelper.isAffixableArmor(stack)
                ?List.of("max_health","armor","armor_toughness","knockback_resistance_percent","movement_speed_percent","leggings_slow_resistance_percent")
                :List.of("attack_speed","attack_range","critical_strike_chance","elemental_damage_percent"))
            affixes.add(new ArpgAffixInstance(id,ArpgAffixTier.T1,roll));
        ArpgWeaponHelper.setWeaponData(stack,new ArpgWeaponData(ArpgItemQuality.LEGENDARY,affixes));
        return stack;
    }
    private static double[] values(ServerPlayer player) {
        double[] out=new double[WATCHED.size()];
        for(int i=0;i<out.length;i++)out[i]=player.getAttribute(WATCHED.get(i))==null?Double.NaN:player.getAttributeValue(WATCHED.get(i));
        return out;
    }
    private static void tick(ServerPlayer player) { player.tickCount++; ArpgPlayerAttributeService.apply(player); }
    /** Runeforged's own result for the current inputs, with the throttle out of the way. */
    private static double[] reference(ServerPlayer player) {
        AttributeThrottle.enabled=false; AttributeThrottle.forget(player);
        try { ArpgPlayerAttributeService.apply(player); return values(player); }
        finally { AttributeThrottle.enabled=true; AttributeThrottle.forget(player); }
    }
    private static void trigger(ServerPlayer player,String name,Runnable change,Map<String,Object> receipt) {
        tick(player);
        long before=AttributeThrottle.full;
        change.run(); tick(player);
        double[] actual=values(player), expected=reference(player);
        receipt.put(name+"_recomputes",AttributeThrottle.full-before);
        check(AttributeThrottle.full>before,name+": change did not force a recompute, delta "+(AttributeThrottle.full-before)+" weapon "+player.getWeaponItem()+" main "+player.getMainHandItem());
        check(Arrays.equals(actual,expected),name+": values "+Arrays.toString(actual)+" != "+Arrays.toString(expected));
        receipt.put(name,Arrays.toString(actual));
    }
    private static void run(MinecraftServer server) throws Exception {
        check(server.getPort()==25566,"Fixture requires private port");
        ServerPlayer player=FakePlayer.get(server.overworld());
        Map<String,Object> receipt=new LinkedHashMap<>();
        double[] bare=reference(player);
        player.setItemSlot(EquipmentSlot.MAINHAND,rolled(Items.DIAMOND_SWORD,server));
        player.setItemSlot(EquipmentSlot.HEAD,rolled(Items.DIAMOND_HELMET,server));
        player.setItemSlot(EquipmentSlot.CHEST,rolled(Items.DIAMOND_CHESTPLATE,server));
        player.setItemSlot(EquipmentSlot.LEGS,rolled(Items.DIAMOND_LEGGINGS,server));
        player.setItemSlot(EquipmentSlot.FEET,rolled(Items.DIAMOND_BOOTS,server));
        player.setItemSlot(EquipmentSlot.OFFHAND,rolled(Items.DIAMOND_AXE,server));
        double[] geared=reference(player);
        receipt.put("bare",Arrays.toString(bare)); receipt.put("geared",Arrays.toString(geared));
        receipt.put("gear_changes_attributes",!Arrays.equals(bare,geared));
        check(!Arrays.equals(bare,geared),"fixture gear must change attributes");

        // Unchanged inputs: one recompute per REFRESH_TICKS, identical values every tick.
        long full0=AttributeThrottle.full, skipped0=AttributeThrottle.skipped;
        for(int i=0;i<100;i++){ tick(player); check(Arrays.equals(values(player),geared),"steady values drifted at tick "+i); }
        receipt.put("steady_full",AttributeThrottle.full-full0); receipt.put("steady_skipped",AttributeThrottle.skipped-skipped0);
        check(AttributeThrottle.full-full0==5&&AttributeThrottle.skipped-skipped0==95,"expected 5 recomputes and 95 skips per 100 ticks");

        trigger(player,"swap_chest",() -> player.setItemSlot(EquipmentSlot.CHEST,rolled(Items.DIAMOND_CHESTPLATE,server)),receipt);
        trigger(player,"swap_weapon",() -> player.setItemSlot(EquipmentSlot.MAINHAND,rolled(Items.NETHERITE_SWORD,server)),receipt);
        trigger(player,"remove_boots",() -> player.setItemSlot(EquipmentSlot.FEET,ItemStack.EMPTY),receipt);
        trigger(player,"damage_helmet_in_place",() -> player.getItemBySlot(EquipmentSlot.HEAD).setDamageValue(100),receipt);
        trigger(player,"slowness_added",() -> player.addEffect(new MobEffectInstance(MobEffects.SLOWNESS,400,1)),receipt);
        trigger(player,"slowness_level_changed",() -> { player.removeEffect(MobEffects.SLOWNESS); player.addEffect(new MobEffectInstance(MobEffects.SLOWNESS,400,3)); },receipt);
        trigger(player,"health_boost_added",() -> player.addEffect(new MobEffectInstance(MobEffects.HEALTH_BOOST,400,2)),receipt);
        trigger(player,"offhand_weapon_applied",() -> ArpgPlayerAttributeService.applyWeapon(player,player.getOffhandItem()),receipt);

        // Cost per player tick: Runeforged alone versus with the throttle, same gear.
        int n=300;
        AttributeThrottle.enabled=false;
        for(int i=0;i<40;i++)tick(player);
        long start=System.nanoTime(); for(int i=0;i<n;i++)tick(player); long original=System.nanoTime()-start;
        AttributeThrottle.enabled=true; AttributeThrottle.forget(player);
        for(int i=0;i<40;i++)tick(player);
        start=System.nanoTime(); for(int i=0;i<n;i++)tick(player); long throttled=System.nanoTime()-start;
        tick(player); check(AttributeThrottle.skip(player),"skip expected right after a recompute");
        for(int i=0;i<20000;i++)AttributeThrottle.skip(player);
        long skipStart=System.nanoTime(); for(int i=0;i<20000;i++)check(AttributeThrottle.skip(player),"steady skip");
        receipt.put("skip_path_us",Math.round((System.nanoTime()-skipStart)/20000.0/10)/100.0);
        long check=System.nanoTime(); for(int i=0;i<n;i++)AttributeThrottle.same(player.getItemBySlot(EquipmentSlot.CHEST),player.getItemBySlot(EquipmentSlot.CHEST).copy());
        receipt.put("same_check_us_per_stack",Math.round((System.nanoTime()-check)/(double)n/10)/100.0);
        receipt.put("original_us_per_tick",Math.round(original/(double)n/10)/100.0);
        receipt.put("throttled_us_per_tick",Math.round(throttled/(double)n/10)/100.0);
        receipt.put("result","pass");
        StringBuilder json=new StringBuilder("{\n");
        int i=0; for(var entry:receipt.entrySet()) {
            Object value=entry.getValue();
            json.append("  \"").append(entry.getKey()).append("\": ").append(value instanceof String ? "\""+value+"\"" : value).append(++i<receipt.size()?",\n":"\n");
        }
        Files.writeString(Path.of("throttle-test-receipt.json"),json.append("}\n").toString());
        System.out.println("THROTTLE_NATIVE_TEST_OK "+json.toString().replace('\n',' '));
    }
}
