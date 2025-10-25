import matplotlib.pyplot as plt

def plot_readings(readings, title):
    plt.figure(figsize=(5,3))
    plt.plot(range(1, len(readings)+1), readings, marker='o')
    plt.title(title)
    plt.xlabel('Reading #')
    plt.ylabel('Distance (cm)')
    plt.grid(True)
    plt.tight_layout()
    plt.show()  # or plt.savefig("shape_plot.png") to save

def test_shape():
    readings = []
    for _ in range(15):
        d,_ = ultrasonic_distance()
        readings.append(d)
        time.sleep(0.2)
    mean_val = statistics.mean(readings)
    std_dev = statistics.stdev(readings)
    shape = "Flat" if std_dev < 0.5 else "Curved" if std_dev < 2 else "Irregular"
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    r,g,b = color.color_rgb_bytes
    conclusion = f"Shape {shape} affects ultrasonic reflection; higher stddev lowers accuracy."
    
    oled_display([
        "Shape Test Done",
        f"Mean: {mean_val:.2f} cm",
        f"StdDev: {std_dev:.2f}",
        f"Shape: {shape}",
        f"T={obj_temp:.1f}/{amb_temp:.1f}C",
        f"RGB={r},{g},{b}",
        conclusion
    ])
    buzzer_beep(2)
    plot_readings(readings, "Shape Test Readings")

def test_material():
    readings = []
    for _ in range(15):
        d,_ = ultrasonic_distance()
        readings.append(d)
        time.sleep(0.2)
    std_dev = statistics.stdev(readings)
    material = "Absorbing" if std_dev > 1 else "Reflective"
    obj_temp = mlx.object_temperature
    amb_temp = mlx.ambient_temperature
    r,g,b = color.color_rgb_bytes
    conclusion = f"Material {material} affects accuracy; absorbing materials scatter waves."
    
    oled_display([
        "Material Test Done",
        f"StdDev: {std_dev:.2f}",
        f"Material: {material}",
        f"T={obj_temp:.1f}/{amb_temp:.1f}C",
        f"RGB={r},{g},{b}",
        conclusion
    ])
    buzzer_beep(2)
    plot_readings(readings, "Material Test Readings")
