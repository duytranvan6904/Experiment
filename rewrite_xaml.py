
new_content = r"""<Window x:Class="Microsoft.Samples.Kinect.BodyBasics.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:local="clr-namespace:Microsoft.Samples.Kinect.BodyBasics"
        Title="Body Basics" 
        Height="800" Width="1440" 
        Loaded="MainWindow_Loaded"
        Closing="MainWindow_Closing">
    <Window.Resources>
        <SolidColorBrush x:Key="MediumGreyBrush" Color="#ff6e6e6e" />
        <SolidColorBrush x:Key="KinectPurpleBrush" Color="#ff52318f" />
        <SolidColorBrush x:Key="KinectBlueBrush" Color="#ff00BCF2" />
    </Window.Resources>
    <Grid Margin="0">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto" />
            <RowDefinition Height="*" />
            <RowDefinition Height="Auto" />
        </Grid.RowDefinitions>

        <!-- Header -->
        <Grid Grid.Row="0" Background="#1e1e2e">
            <Image Source="Images\Logo.png" HorizontalAlignment="Left" Stretch="Fill" Height="32" Width="81" Margin="10,5,0,5" />
            <TextBlock HorizontalAlignment="Right" VerticalAlignment="Center" Foreground="#6c7086" FontFamily="Segoe UI" FontSize="14" Margin="0,0,10,0">Body Basics – Prediction Evaluation</TextBlock>
        </Grid>

        <!-- Main Content: 3 columns -->
        <Grid Grid.Row="1" Background="#11111b">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="260" />
                <ColumnDefinition Width="*" />
                <ColumnDefinition Width="1.5*" />
            </Grid.ColumnDefinitions>

            <!-- 1. LEFT COLUMN: Controls -->
            <Border Grid.Column="0" Background="#181825" BorderBrush="#313244" BorderThickness="0,0,1,0">
                <ScrollViewer VerticalScrollBarVisibility="Auto" Margin="8,8,8,4">
                    <StackPanel>
                        <TextBlock FontSize="14" FontWeight="Bold" Foreground="#89b4fa" Margin="0,0,0,6">Experiment Controls</TextBlock>

                        <!-- ROS Connection -->
                        <StackPanel Orientation="Horizontal" Margin="0,0,0,6">
                            <TextBlock VerticalAlignment="Center" Foreground="#cdd6f4" Margin="0,0,4,0" FontSize="11">ROS IP:</TextBlock>
                            <TextBox Name="txtRosIp" Width="100" Text="10.98.106.246" FontSize="11"/>
                            <Button Name="btnConnectRos" Width="55" Margin="4,0,0,0" Click="BtnConnectRos_Click" FontSize="10">Connect</Button>
                        </StackPanel>

                        <!-- Threshold Settings -->
                        <GroupBox Header="Settings" Foreground="#89b4fa" Margin="0,0,0,6" Padding="4" FontSize="11">
                            <StackPanel>
                                <StackPanel Orientation="Horizontal" Margin="0,0,0,4">
                                    <TextBlock Foreground="#cdd6f4" Width="72" VerticalAlignment="Center">Y-Threshold:</TextBlock>
                                    <TextBox Name="txtYThreshold" Width="50" Text="0.5" />
                                </StackPanel>
                                <StackPanel Orientation="Horizontal" Margin="0,0,0,4">
                                    <TextBlock Foreground="#cdd6f4" Width="72" VerticalAlignment="Center">Max Frames:</TextBlock>
                                    <TextBox Name="txtMaxFrames" Width="50" Text="0" />
                                </StackPanel>
                                <StackPanel Orientation="Horizontal">
                                    <TextBlock Foreground="#cdd6f4" Width="72" VerticalAlignment="Center">Max Time:</TextBlock>
                                    <TextBox Name="txtMaxTime" Width="50" Text="0" />
                                </StackPanel>
                            </StackPanel>
                        </GroupBox>

                        <!-- Prediction Buttons -->
                        <StackPanel Orientation="Horizontal" Margin="0,0,0,6">
                            <Button Name="btnStart" Width="115" Margin="0,0,4,0" Click="BtnStart_Click" 
                                    Background="#a6e3a1" Foreground="#1e1e2e" FontWeight="Bold" FontSize="10">▶ Start Pred</Button>
                            <Button Name="btnStop" Width="115" Click="BtnStop_Click" 
                                    Background="#f38ba8" Foreground="#1e1e2e" FontWeight="Bold" FontSize="10">■ Stop</Button>
                        </StackPanel>

                        <Button Name="btnCalibrate" Margin="0,0,0,6" Click="BtnCalibrate_Click" 
                                Background="#313244" Foreground="#cdd6f4" FontSize="11" Padding="4,2">Calibrate Origin</Button>

                        <!-- Coordinates Display -->
                        <TextBlock Name="txtXYZ" Text="X: -, Y: -, Z: -" Foreground="#f5e0dc" FontWeight="Bold" FontSize="11" Margin="0,0,0,2"/>
                        <TextBlock Name="txtPredXYZ" Text="Pred: X: -, Y: -, Z: -" Foreground="#f38ba8" FontWeight="Bold" FontSize="11" Margin="0,0,0,6"/>

                        <!-- Status -->
                        <GroupBox Header="Experiment Info" Foreground="#89b4fa" Padding="4" FontSize="11" Margin="0,0,0,6">
                            <StackPanel>
                                <TextBlock Name="lblBody" Text="Body: Not tracked" Foreground="#cdd6f4"/>
                                <TextBlock Name="txtCurrentScenario" Text="Scenario: None" Foreground="#89b4fa" FontWeight="Bold"/>
                                <TextBlock Name="lblRecording" Text="Session: Inactive" Foreground="#fab387"/>
                            </StackPanel>
                        </GroupBox>
                        
                        <GroupBox Header="Event Log" Foreground="#89b4fa" Padding="4" FontSize="11" Margin="0,0,0,6">
                            <ListBox Name="lstLog" Height="100" Background="#1e1e2e" Foreground="#cdd6f4" BorderThickness="0" FontSize="10">
                                <ListBox.ItemContainerStyle>
                                    <Style TargetType="ListBoxItem">
                                        <Setter Property="Padding" Value="2,1"/>
                                    </Style>
                                </ListBox.ItemContainerStyle>
                            </ListBox>
                        </GroupBox>

                        <!-- Model Selection -->
                        <GroupBox Header="Model" Foreground="#89b4fa" Padding="4" FontSize="10" Margin="0,0,0,6">
                            <StackPanel Orientation="Horizontal">
                                <RadioButton Name="rbGru" Content="GRU" IsChecked="True" Checked="Model_Checked" Foreground="#cdd6f4" Margin="0,0,6,0"/>
                                <RadioButton Name="rbRnn" Content="RNN" Checked="Model_Checked" Foreground="#cdd6f4" Margin="0,0,6,0"/>
                                <RadioButton Name="rbLstm" Content="LSTM" Checked="Model_Checked" Foreground="#cdd6f4"/>
                            </StackPanel>
                        </GroupBox>

                        <!-- Performance -->
                        <GroupBox Header="Performance" Foreground="#89b4fa" Padding="4" FontSize="10" Margin="0,0,0,6">
                            <StackPanel>
                                <TextBlock Name="lblActiveModel" Text="Model: GRU" Foreground="#a6e3a1"/>
                                <TextBlock Name="lblBufferStatus" Text="Buffer: 0/20" Foreground="#fab387"/>
                                <TextBlock Name="lblInferenceTime" Text="Inference: 0.0ms" Foreground="#f5e0dc"/>
                                <TextBlock Name="lblBridgeStatus" Text="Bridge: Disconnected" Foreground="#f38ba8"/>
                                <TextBlock Name="lblMAE" Text="MAE: -" Foreground="#89dceb"/>
                                <TextBlock Name="lblMSE" Text="MSE: -" Foreground="#89dceb"/>
                            </StackPanel>
                        </GroupBox>

                        <TextBlock Name="txtSavePath" Text="-" TextWrapping="Wrap" FontSize="8" Foreground="#585b70" Margin="0,4,0,0"/>
                        <Button Name="btnResetPlots" Content="Reset Graphs" Click="BtnResetPlots_Click" 
                                Margin="0,4,0,0" Background="#313244" Foreground="#cdd6f4" FontSize="10" Padding="4,2"/>
                    </StackPanel>
                </ScrollViewer>
            </Border>

            <!-- 2. CENTER COLUMN: Camera at Top -->
            <Grid Grid.Column="1" Background="#11111b" Margin="15,0,15,0">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="*" />
                </Grid.RowDefinitions>

                <Border Grid.Row="0" Margin="0,15,0,15" Background="#181825" BorderBrush="#313244" BorderThickness="1" CornerRadius="8" Padding="4" VerticalAlignment="Top">
                    <StackPanel>
                        <TextBlock Text="KINETC V2 LIVE FEED" Foreground="#89b4fa" FontSize="10" FontFamily="Segoe UI" Margin="0,0,0,4" HorizontalAlignment="Center" FontWeight="Bold"/>
                        <Viewbox Stretch="Uniform" MaxHeight="360">
                            <Grid>
                                <Image Source="{Binding ColorImageSource}" Stretch="Uniform" />
                                <Image Source="{Binding ImageSource}" Stretch="Uniform" />
                            </Grid>
                        </Viewbox>
                    </StackPanel>
                </Border>
                
                <Border Grid.Row="1" Margin="0,0,0,15" BorderBrush="#313244" BorderThickness="1" BorderDashArray="4 4" CornerRadius="8" Background="#181825">
                    <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
                        <TextBlock Text="RESERVED FOR DESTINATION ANALYSIS" Foreground="#45475a" FontSize="14" HorizontalAlignment="Center"/>
                        <TextBlock Text="(Area will contain future probability plots)" Foreground="#313244" FontSize="10" HorizontalAlignment="Center" Margin="0,4,0,0"/>
                    </StackPanel>
                </Border>
            </Grid>

            <!-- 3. RIGHT COLUMN: Trajectory Dashboard -->
            <Border Grid.Column="2" Background="#181825" BorderBrush="#313244" BorderThickness="1,0,0,0">
                <Grid Margin="10">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="*"/>
                        <RowDefinition Height="*"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>
                    <local:TrajectoryPlot x:Name="plotX" Title="X-Axis Trajectory" Grid.Row="0" Margin="0,0,0,10"/>
                    <local:TrajectoryPlot x:Name="plotY" Title="Y-Axis Trajectory" Grid.Row="1" Margin="0,0,0,10"/>
                    <local:TrajectoryPlot x:Name="plotZ" Title="Z-Axis Trajectory" Grid.Row="2"/>
                </Grid>
            </Border>
        </Grid>

        <!-- Status Bar -->
        <StatusBar Grid.Row="2" Background="#1e1e2e" Foreground="#6c7086">
            <StatusBarItem Content="Ready" Name="statusBar"/>
        </StatusBar>
    </Grid>
</Window>
"""

with open('e:/Downloads/BodyBasics-WPF/Experiment/MainWindow.xaml', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("MainWindow.xaml rewritten successfully!")
