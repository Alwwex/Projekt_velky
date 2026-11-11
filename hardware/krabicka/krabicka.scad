// =============================================================================
//  LaserPlan – krabička pro 3D tisk (OpenSCAD)
//
//  Díly:   part = "spodek"   – vana s distančními sloupky, držákem laseru a baterie
//          part = "vicko"    – víko s okénkem pro OLED, otvory pro tlačítka a LED
//          part = "hmatnik"  – hmatník tlačítka (tisknout 2×)
//          part = "sestava"  – náhled celé sestavy (netisknout)
//
//  Export:  openscad -D 'part="spodek"' -o spodek.stl krabicka.scad
//
//  Souřadnice X/Y odpovídají desce plošného spoje při pohledu shora:
//  X = 0 přední hrana DPS (u laseru), X = 90 zadní hrana (USB-C),
//  Y = 0 spodní hrana DPS (konektory laseru a baterie), Y = 44 horní hrana (vypínač).
//
//  Tisk: PETG nebo PLA, 0,2 mm vrstva, 3 perimetry, 20 % výplň.
//  Spodek tiskni dnem dolů, víko vrchem dolů (okénko na podložce), bez podpor.
// =============================================================================

part = "sestava";

// ---------------------------------------------------------------- parametry
pcb_l = 90;  pcb_w = 44;  pcb_t = 1.6;
holes = [[3.2, 3.2], [86.8, 3.2], [3.2, 40.8], [86.8, 40.8]];   // díry M2.5 (souř. DPS shora)

wall = 2.0;     floor_t = 2.0;    lid_t = 2.0;
clr = 0.5;      // vůle mezi DPS a stěnou
chan = 3.0;     // kabelový kanál podél spodní hrany DPS (laser + baterie)
below = 16;     // výška prostoru pod DPS (laser modul 13 mm + vývody THT)
above = 14;     // výška prostoru nad DPS (OLED na dutinkové liště, tlačítka 13 mm)
corner_r = 4;

// laserový modul – ZMĚŘ SVŮJ MODUL a uprav (délka, šířka, výška)
laser = [48, 25, 13];
laser_y = 22;             // osa modulu (Y)
laser_win = [21, 11];     // okénko pro optiku v přední stěně (šířka, výška)

// Li-Pol baterie (např. 803040 = 8 × 30 × 40 mm, 1000 mAh)
bat = [40, 30, 8];
bat_x = 49;               // začátek baterie (X)

// prvky na DPS (souřadnice desky shora, Y od spodní hrany = 44 - y v KiCadu)
oled_win  = [[8, 44 - 32.5], [22, 44 - 7.5]];   // okénko OLED [min], [max]
btn_mode  = [37.75, 44 - 13.75];                // REŽIM (SW3)
btn_meas  = [37.75, 44 - 24.75];                // MĚŘIT (SW2)
led_bt    = [45.0, 44 - 29.0];                  // modrá LED
led_chg   = [[86.7, 44 - 34.0], [86.7, 44 - 36.5]];  // nabíjení
buzzer    = [39.3, 44 - 37.6];
usb_y     = 44 - 24.0;                          // osa USB-C
sw_x      = 20.0;                               // páčka vypínače (horní hrana DPS)

btn_hole = 7.6;  btn_top = 13;     // tlačítka 6×6 mm, výška 13 mm nad DPS
screw_d = 2.8;   pilot_d = 2.1;    head_d = 5.2;  head_h = 1.6;   // šrouby M2.5×30

$fn = 48;

// ---------------------------------------------------------------- odvozené
in_x0 = -clr;                 in_x1 = pcb_l + clr;
in_y0 = -clr - chan;          in_y1 = pcb_w + clr;
out_x0 = in_x0 - wall;        out_x1 = in_x1 + wall;
out_y0 = in_y0 - wall;        out_y1 = in_y1 + wall;
z_pcb = floor_t + below;              // spodní plocha DPS
z_split = z_pcb + pcb_t;              // dělicí rovina = horní plocha DPS
z_top = z_split + above + lid_t;      // vrch víka

echo(str("Vnější rozměry: ", out_x1 - out_x0, " × ", out_y1 - out_y0, " × ", z_top, " mm"));
echo(str("Offset ZADNÍ hrany (firmware rear): ", out_x1 - in_x0, " mm"));
echo(str("Offset PŘEDNÍ hrany (firmware front): ", -wall, " mm"));

module rounded_box(x0, y0, x1, y1, z0, z1, r) {
    translate([0, 0, z0]) hull()
        for (x = [x0 + r, x1 - r], y = [y0 + r, y1 - r])
            translate([x, y, 0]) cylinder(r = r, h = z1 - z0);
}

module shell(z0, z1) {
    difference() {
        rounded_box(out_x0, out_y0, out_x1, out_y1, z0, z1, corner_r);
        rounded_box(in_x0, in_y0, in_x1, in_y1, z0 - 1, z1 + 1, max(0.5, corner_r - wall));
    }
}

// otvory společné pro obě poloviny (protínají dělicí rovinu)
module side_cuts() {
    // USB-C: otvor + kapsa zvenku pro koncovku kabelu
    translate([in_x1 - 1, usb_y - 4.7, z_split - 0.2]) cube([wall + 2, 9.4, 3.8]);
    translate([out_x1 - 0.8, usb_y - 6.5, z_split + 1.6 - 4]) cube([2, 13, 8]);
    // páčka vypínače (horní strana)
    translate([sw_x - 3.2, in_y1 - 1, z_split - 0.2]) cube([6.4, wall + 2, 4.2]);
    // okénko laseru v přední stěně
    translate([out_x0 - 1, laser_y - laser_win[0] / 2, floor_t + laser[2] / 2 - laser_win[1] / 2])
        cube([wall + 2, laser_win[0], laser_win[1]]);
}

// ---------------------------------------------------------------- spodek
module spodek() {
    difference() {
        union() {
            // dno
            rounded_box(out_x0, out_y0, out_x1, out_y1, 0, floor_t, corner_r);
            shell(0, z_split);
            // distanční sloupky pod DPS
            for (h = holes) translate([h[0], h[1], 0]) cylinder(d = 6, h = z_pcb);
            // vodítka laser modulu
            for (s = [-1, 1])
                translate([in_x0, laser_y + s * (laser[1] / 2 + 0.3) - (s < 0 ? 1.2 : 0), 0])
                    cube([laser[0] * 0.7, 1.2, floor_t + 5]);
            translate([in_x0 + laser[0] + 0.4, laser_y - laser[1] / 2, 0]) cube([1.2, 6, floor_t + 5]);
            translate([in_x0 + laser[0] + 0.4, laser_y + laser[1] / 2 - 6, 0]) cube([1.2, 6, floor_t + 5]);
            // ohrádka baterie (rohy)
            for (cx = [bat_x - 1.2, bat_x + bat[0]], cy = [laser_y - bat[1] / 2 - 1.2, laser_y + bat[1] / 2])
                translate([cx, cy, 0]) cube([1.2, 1.2, floor_t + 4]);
        }
        for (h = holes) translate([h[0], h[1], floor_t]) cylinder(d = pilot_d, h = z_pcb);
        side_cuts();
        // nápis na dně
        translate([pcb_l / 2, pcb_w / 2 - chan / 2, -0.01]) mirror([1, 0, 0])
            linear_extrude(0.6) text("LaserPlan", size = 7, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
}

// ---------------------------------------------------------------- víko
module vicko() {
    difference() {
        union() {
            shell(z_split, z_top);
            rounded_box(out_x0, out_y0, out_x1, out_y1, z_top - lid_t, z_top, corner_r);
            // přítlačné sloupky na DPS
            for (h = holes) translate([h[0], h[1], z_split + 0.2]) cylinder(d = 6, h = above);
        }
        // šrouby M2.5 se zápustnou hlavou
        for (h = holes) {
            translate([h[0], h[1], z_split - 1]) cylinder(d = screw_d, h = above + lid_t + 2);
            translate([h[0], h[1], z_top - head_h]) cylinder(d = head_d, h = head_h + 1);
        }
        // okénko OLED se zkosením
        hull() {
            translate([oled_win[0][0], oled_win[0][1], z_top - lid_t - 0.1])
                cube([oled_win[1][0] - oled_win[0][0], oled_win[1][1] - oled_win[0][1], 0.1]);
            translate([oled_win[0][0] - 1.5, oled_win[0][1] - 1.5, z_top])
                cube([oled_win[1][0] - oled_win[0][0] + 3, oled_win[1][1] - oled_win[0][1] + 3, 0.1]);
        }
        // tlačítka
        for (b = [btn_mode, btn_meas]) translate([b[0], b[1], z_top - lid_t - 1]) cylinder(d = btn_hole, h = lid_t + 2);
        // LED
        for (l = concat([led_bt], led_chg)) translate([l[0], l[1], z_top - lid_t - 1]) cylinder(d = 2.4, h = lid_t + 2);
        // bzučák
        for (dx = [-3, 0, 3], dy = [-3, 0, 3]) if (abs(dx) + abs(dy) < 6)
            translate([buzzer[0] + dx, buzzer[1] + dy, z_top - lid_t - 1]) cylinder(d = 1.6, h = lid_t + 2);
        side_cuts();
        // popisky (vylisované)
        translate([btn_meas[0], btn_meas[1] - 6.2, z_top - 0.5]) linear_extrude(1)
            text("MERIT", size = 2.6, halign = "center", font = "Liberation Sans:style=Bold");
        translate([btn_mode[0], btn_mode[1] + 4.6, z_top - 0.5]) linear_extrude(1)
            text("REZIM", size = 2.6, halign = "center", font = "Liberation Sans:style=Bold");
        translate([led_bt[0], led_bt[1] - 4.6, z_top - 0.5]) linear_extrude(1)
            text("BT", size = 2.4, halign = "center", font = "Liberation Sans:style=Bold");
        // šipka směru laseru
        translate([out_x0 + 4, pcb_w / 2 - chan / 2, z_top - 0.5]) linear_extrude(1)
            polygon([[0, 0], [5, 3], [5, -3]]);
    }
}

// ---------------------------------------------------------------- hmatník tlačítka
module hmatnik() {
    gap_under_lid = above - btn_top;                 // 1 mm mezi tlačítkem a víkem
    cylinder(d = 10, h = gap_under_lid - 0.25);      // límec pod víkem (nevypadne)
    cylinder(d = btn_hole - 0.5, h = gap_under_lid + lid_t + 1.5);
}

// ---------------------------------------------------------------- náhled
module pcb_preview() {
    color("darkgreen") translate([0, 0, z_pcb]) cube([pcb_l, pcb_w, pcb_t]);
    color("dimgray") translate([in_x0, laser_y - laser[1] / 2, floor_t]) cube(laser);
    color("silver") translate([bat_x, laser_y - bat[1] / 2, floor_t]) cube(bat);
    color("black") translate([4, 44 - 33.6, z_split + 11]) cube([27.8, 27.3, 1.5]);
}

if (part == "spodek") spodek();
else if (part == "vicko") translate([0, 0, z_top]) mirror([0, 0, 1]) vicko();   // vrchem dolů
else if (part == "hmatnik") hmatnik();
else {
    color("orange", 0.9) spodek();
    pcb_preview();
    color("orange", 0.55) translate([0, 0, 6]) vicko();
    for (b = [btn_mode, btn_meas]) color("white") translate([b[0], b[1], z_split + btn_top + 6]) hmatnik();
}
