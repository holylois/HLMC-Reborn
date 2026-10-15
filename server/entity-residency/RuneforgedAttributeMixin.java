package holylois.residency.runeforged;

import com.ultimatearpg.combat.ArpgPlayerAttributeService;
import holylois.residency.AttributeThrottle;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Server players only: clients keep Runeforged's own per-tick recompute. */
@Mixin(ArpgPlayerAttributeService.class)
public abstract class RuneforgedAttributeMixin {
    @Inject(method="apply", at=@At("HEAD"), cancellable=true, require=1)
    private static void holyLoisSkipUnchanged(Player player, CallbackInfo callback) {
        if(player instanceof ServerPlayer serverPlayer&&AttributeThrottle.skip(serverPlayer))callback.cancel();
    }
    @Inject(method="apply", at=@At("RETURN"), require=1)
    private static void holyLoisApplied(Player player, CallbackInfo callback) {
        if(player instanceof ServerPlayer serverPlayer)AttributeThrottle.applied(serverPlayer);
    }
    @Inject(method="applyWeapon", at=@At("HEAD"), require=1)
    private static void holyLoisWeaponApplied(Player player, ItemStack weapon, CallbackInfo callback) {
        if(player instanceof ServerPlayer serverPlayer)AttributeThrottle.weaponApplied(serverPlayer);
    }
}
